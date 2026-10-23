"""Simulator API: real orders through the original algorithm, compared with not using it."""
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from conftest import DEMO

ORIG = Path(__file__).resolve().parents[2] / "cpp-packer-service" / "original" / "packer.cpp"


def test_requires_staff(app_client, customer):
    assert app_client.get("/api/sim/orders").status_code == 401
    assert app_client.get("/api/sim/orders", headers=customer).status_code == 403


def test_order_simulation_and_comparison(app_client, worker, place_order):
    order = place_order(DEMO)
    assert any(o["id"] == order["id"] for o in app_client.get("/api/sim/orders", headers=worker).json())
    r = app_client.get(f"/api/sim/orders/{order['id']}", headers=worker)
    assert r.status_code == 200, r.text
    d = r.json()
    a = d["algorithm"]
    assert a["box_cm"] == [10.0, 13.5, 14.0]
    sw = a["sweep"]
    assert len(sw["trials"]) == 200 and sw["trials"][sw["best"]]["box_cm"] == a["box_cm"]
    # the best trial really is the smallest score among the trials that fit
    assert len(a["steps"]) == 5 and a["steps"][0]["name"].startswith("Rose Oud")
    row, stock = d["without"]
    assert row["box_cm"][0] == sum(u["padded_cm"][0] for u in d["units"])     # side by side
    assert stock["available"] and stock["carton"] == "Medium Apparel / Electronics"
    assert a["volume_cm3"] < row["volume_cm3"] and a["volume_cm3"] < stock["volume_cm3"]
    assert all(c["volume_saved_cm3"] > 0 for c in d["comparisons"])
    assert a["fill"] > row["fill"] and a["fill"] > stock["fill"]


def test_custom_mix_and_summary(app_client, worker, place_order):
    pid = app_client.get("/api/products/orbit-smartwatch").json()["id"]
    lip = app_client.get("/api/products/velvet-matte-lipstick").json()["id"]
    r = app_client.post("/api/sim/custom", headers=worker, json={"items": [{"product_id": pid, "quantity": 1},
                                                                          {"product_id": lip, "quantity": 3}]})
    assert r.status_code == 200 and len(r.json()["units"]) == 4
    place_order(DEMO)
    s = app_client.get("/api/sim/summary", headers=worker).json()
    assert s["totals"]["orders"] == 1 and s["totals"]["algorithm_cm3"] < s["totals"]["single_row_cm3"]


def test_sweep_matches_original_program(packer_url, tmp_path):
    exe = tmp_path / ("orig.exe" if sys.platform == "win32" else "orig")
    if subprocess.run(["g++", "-O2", "-std=c++17", str(ORIG), "-o", str(exe)], capture_output=True).returncode:
        pytest.skip("g++ not available to compile the original program")
    items = [(100, 70, 140), (70, 50, 140), (25, 25, 85), (15, 15, 130), (15, 15, 130)]
    out = subprocess.run([str(exe)], input=f"{len(items)}\n" + "\n".join(" ".join(map(str, i)) for i in items),
                         capture_output=True, text=True).stdout.split("\n")
    W, L, H = map(int, out[0].split())
    d = httpx.post(packer_url + "/v1/pack/sweep",
                   json={"items": [{"id": f"i{k}", "l": a, "w": b, "h": c} for k, (a, b, c) in enumerate(items)]}).json()
    assert (d["box"]["W"], d["box"]["L"], d["box"]["H"]) == (W, L, H)
    orig = {f"i{k}": list(map(int, ln.split()))[1:3] for k, ln in enumerate(out[1:1 + len(items)])}
    assert {p["id"]: [p["x"], p["y"]] for p in d["placements"]} == orig


def test_public_sim_data_feed(app_client, place_order):
    place_order(DEMO)
    r = app_client.get("/api/public/sim-data", headers={"Origin": "http://localhost:5175"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5175"
    d = r.json()
    assert len(d["products"]) == 30 and all(len(p["dims_cm"]) == 3 for p in d["products"])
    # sorted by internal volume (6.9 L before 7.8 L, etc.)
    assert [c["name"] for c in d["cartons"]] == ["Ultra-Small / Cosmetics", "Small Mailer / Accessories", "Medium Mailer / Skincare Kit", "Standard E-commerce Box", "Shoe Box / Small Gadgets", "Heavy Gadget Carrier", "Medium Apparel / Electronics", "Large Multi-Item Box"]
    assert d["rules"]["fragile_min_padding_cm"] == 1.0 and d["rules"]["glue_flap_cm"] == 3.5
    assert d["orders"] and all(set(o) == {"code", "status", "created_at", "items"} for o in d["orders"])
    assert '"address"' not in r.text and '"contact"' not in r.text and '"customer"' not in r.text  # no customer details
