"""Test fixtures.

Tests use a fresh temporary SQLite database and the REAL C++ packing service,
started on a free port, so FastAPI-to-C++ HTTP communication is exercised for real.
Build the service first (cpp-packer-service/build.bat or build.sh). If the binary
is missing, packing tests are skipped with a clear message.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "cpp-packer-service" / "build" / ("packer_service.exe" if sys.platform == "win32" else "packer_service")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def packer_url():
    if os.getenv("TEST_PACKER_URL"):
        yield os.environ["TEST_PACKER_URL"]
        return
    if not EXE.exists():
        pytest.skip(f"C++ packer not built ({EXE}). Run cpp-packer-service/build.bat first.")
    port = _free_port()
    proc = subprocess.Popen([str(EXE), str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            httpx.get(url + "/health", timeout=0.5)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield url
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture()
def app_client(request, tmp_path, packer_url, monkeypatch):
    from app import database
    from app.config import settings

    monkeypatch.setattr(settings, "packer_url", packer_url)
    monkeypatch.setattr(settings, "worker_code", "TEST-CODE")
    monkeypatch.setattr(settings, "admin_access_code", ADMIN_CODE)
    monkeypatch.setattr(settings, "seed_demo_order", False)
    monkeypatch.setattr(settings, "seed_sample_carton_values", True)
    monkeypatch.setattr(settings, "packing_algorithm", "optimizer")   # the shipped default
    from app.security import admin_throttle
    admin_throttle._fails.clear()
    database.configure(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")

    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


ADMIN_CODE = "Test-Admin-Code-9"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def worker(app_client):
    r = app_client.post("/api/auth/worker", json={"code": "TEST-CODE", "worker_name": "Tester"})
    assert r.status_code == 200
    return _auth(r.json()["token"])


@pytest.fixture()
def admin(app_client):
    r = app_client.post("/api/auth/admin", json={"code": ADMIN_CODE})
    assert r.status_code == 200, r.text
    return _auth(r.json()["token"])


@pytest.fixture()
def customer(app_client):
    r = app_client.post("/api/auth/register", json={"name": "Asha", "email": "asha@example.com",
                                                      "password": "secret-pass-1"})
    assert r.status_code == 201
    return _auth(r.json()["token"])


CHECKOUT = {"contact": {"name": "Asha", "email": "asha@example.com", "phone": "9876543210"},
            "address": {"line1": "1 Test Road", "city": "Chennai", "state": "TN", "postal_code": "600001"},
            "payment": {"method": "card", "confirm_simulated": True}}


@pytest.fixture()
def place_order(app_client, customer):
    """place_order({slug: qty}) -> order dict"""
    def _place(lines: dict):
        for slug, qty in lines.items():
            pid = app_client.get(f"/api/products/{slug}").json()["id"]
            r = app_client.put(f"/api/me/cart/{pid}", json={"quantity": qty}, headers=customer)
            assert r.status_code == 200, r.text
        r = app_client.post("/api/orders/checkout", json=CHECKOUT, headers=customer)
        assert r.status_code == 201, r.text
        return r.json()
    return _place


DEMO = {"velvet-matte-lipstick": 1, "gentle-nail-polish-remover": 1, "precision-liquid-eyeliner": 2,
        "rose-oud-eau-de-parfum": 1}
FULL_CHECKLIST = {"items_match_order": True, "fragile_protection_applied": True, "placement_followed": True,
                  "void_fill_added": True, "carton_sealed": True}


@pytest.fixture()
def original_algorithm(app_client, monkeypatch):
    """Run a test with the original packer.cpp algorithm (PACKING_ALGORITHM=original)."""
    from app.config import settings
    monkeypatch.setattr(settings, "packing_algorithm", "original")
