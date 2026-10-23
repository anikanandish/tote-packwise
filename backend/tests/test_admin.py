"""Admin console: access-code sign-in, protection of admin routes, orders, reports, duplicate-safe checkout."""
from conftest import ADMIN_CODE, CHECKOUT, DEMO, FULL_CHECKLIST


def _recommend(client, worker, order_id):
    r = client.post(f"/api/packwise/orders/{order_id}/recommend", headers=worker)
    assert r.status_code == 200, r.text
    return r.json()


def test_admin_code_login_logout_and_no_leak(app_client, caplog):
    assert app_client.post("/api/auth/admin", json={"code": "wrong"}).status_code == 401
    r = app_client.post("/api/auth/admin", json={"code": ADMIN_CODE})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert app_client.get("/api/auth/me", headers=h).json()["role"] == "admin"
    s = app_client.get("/api/admin/settings", headers=h)
    assert s.json()["admin_code_configured"] is True
    # the code itself never appears in responses or logs
    for path in ("/api/admin/settings", "/api/admin/audit", "/api/admin/dashboard"):
        assert ADMIN_CODE not in app_client.get(path, headers=h).text
    assert ADMIN_CODE not in caplog.text
    assert app_client.post("/api/auth/logout", headers=h).json() == {"ok": True}
    assert app_client.get("/api/admin/dashboard", headers=h).status_code == 401


def test_admin_routes_protected_on_the_server(app_client, customer, worker):
    for path in ("/api/admin/dashboard", "/api/admin/cartons", "/api/admin/orders", "/api/admin/reports",
                 "/api/admin/products"):
        assert app_client.get(path).status_code == 401
        assert app_client.get(path, headers=customer).status_code == 403
        assert app_client.get(path, headers=worker).status_code == 403
    assert app_client.post("/api/admin/cartons", headers=customer, json={}).status_code in (403, 422)


def test_wrong_codes_are_throttled(app_client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "admin_login_max_failures", 3)
    for _ in range(3):
        assert app_client.post("/api/auth/admin", json={"code": "nope"}).status_code == 401
    r = app_client.post("/api/auth/admin", json={"code": ADMIN_CODE})
    assert r.status_code == 429          # even the right code waits out the lockout


def test_admin_console_locked_without_code(app_client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "admin_access_code", "")
    r = app_client.post("/api/auth/admin", json={"code": "anything"})
    assert r.status_code == 503 and "ADMIN_ACCESS_CODE" in r.json()["detail"]


def test_orders_list_and_detail_with_packing_results(app_client, worker, admin, place_order):
    order = place_order(DEMO)
    other = place_order({"cedar-reed-diffuser": 1})
    plan = _recommend(app_client, worker, order["id"])
    _recommend(app_client, worker, other["id"])
    app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker)
    app_client.post(f"/api/packwise/plans/{plan['id']}/complete", headers=worker, json={"checklist": FULL_CHECKLIST})

    rows = app_client.get("/api/admin/orders", headers=admin).json()
    by_code = {r["code"]: r for r in rows}
    assert by_code[order["code"]]["plan"]["status"] == "completed"
    assert by_code[order["code"]]["plan"]["carton_code"] == "STD-06"
    assert by_code[other["code"]]["plan"]["status"] == "no_fit"
    assert [r["code"] for r in app_client.get("/api/admin/orders", params={"packing": "no_fit"},
                                              headers=admin).json()] == [other["code"]]
    assert [r["code"] for r in app_client.get("/api/admin/orders", params={"q": order["code"]},
                                              headers=admin).json()] == [order["code"]]
    assert [r["code"] for r in app_client.get("/api/admin/orders", params={"carton": "STD-06"},
                                              headers=admin).json()] == [order["code"]]

    d = app_client.get(f"/api/admin/orders/{order['id']}", headers=admin).json()
    assert d["current_plan_id"] == plan["id"] and d["completion"]["carton_code"] == "STD-06"
    assert len(d["order"]["items"]) == 4 and d["order"]["items"][0]["packaging"]["length_cm"] > 0
    assert any(a["action"] == "completed" for a in d["audit"])
    full = app_client.get(f"/api/packwise/plans/{plan['id']}", headers=admin).json()
    # the coordinates shown come from the engine's own JSON
    eng = next(r for r in full["engine"]["response_results"] if r["carton_id"] == f"C{full['carton']['id']}")
    by_ref = {p["unit_ref"]: p for p in full["placements"]}
    for p in eng["placements"]:
        assert round(p["x"] / 10, 1) == by_ref[p["id"]]["x"] and round(p["y"] / 10, 1) == by_ref[p["id"]]["y"]


def test_reports_filters_and_sustainability(app_client, worker, admin, place_order):
    for lines in (DEMO, {"velvet-matte-lipstick": 1}):
        o = place_order(lines)
        plan = _recommend(app_client, worker, o["id"])
        app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker)
        app_client.post(f"/api/packwise/plans/{plan['id']}/complete", headers=worker, json={"checklist": FULL_CHECKLIST})
    r = app_client.get("/api/admin/reports", headers=admin).json()
    assert r["totals"]["orders"] == 2
    assert {u["code"] for u in r["carton_usage"]} == {"STD-06", "STD-02"}
    s = r["sustainability"]
    assert s["calculated"]["volume_reduction_cm3"] == round(
        2 * 46 * 36 * 20 - (36 * 25 * 15 + 20 * 15 * 10), 1)                 # vs the STD-07 baseline
    assert s["estimated"]["board_m2"] > 0 and r["sample_priced_orders"] == 2
    only = app_client.get("/api/admin/reports", params={"carton": "STD-02"}, headers=admin).json()
    assert only["totals"]["orders"] == 1 and only["rows"][0]["carton"] == "STD-02"


def test_checkout_is_idempotent(app_client, customer):
    pid = app_client.get("/api/products/velvet-matte-lipstick").json()["id"]
    stock0 = app_client.get("/api/products/velvet-matte-lipstick").json()["stock"]
    app_client.put(f"/api/me/cart/{pid}", json={"quantity": 2}, headers=customer)
    h = customer | {"Idempotency-Key": "chk-123"}
    a = app_client.post("/api/orders/checkout", json=CHECKOUT, headers=h)
    b = app_client.post("/api/orders/checkout", json=CHECKOUT, headers=h)
    assert a.status_code == 201 and b.status_code == 201 and a.json()["code"] == b.json()["code"]
    assert len(app_client.get("/api/orders", headers=customer).json()) == 1
    assert app_client.get("/api/products/velvet-matte-lipstick").json()["stock"] == stock0 - 2   # deducted once
    # a second submit without the key finds the bag already checked out
    assert app_client.post("/api/orders/checkout", json=CHECKOUT, headers=customer).status_code == 400


def test_password_login_cannot_open_admin(app_client):
    from app import database
    from app.models import User
    from app.security import hash_password
    db = database.SessionLocal()
    db.add(User(email="old-admin@test.local", name="Old admin", password_hash=hash_password("Old-pass-123"), role="admin"))
    db.commit()
    db.close()
    r = app_client.post("/api/auth/login", json={"email": "old-admin@test.local", "password": "Old-pass-123"})
    assert r.status_code == 403
