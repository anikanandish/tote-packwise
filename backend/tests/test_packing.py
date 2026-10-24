"""Packing feasibility, reservations, completion, overrides and reports - against the real C++ service."""
import threading

import httpx
import pytest

from conftest import DEMO, FULL_CHECKLIST


def _carton_id(client, admin, code):
    return next(c["id"] for c in client.get("/api/admin/cartons", headers=admin).json() if c["code"] == code)


def _material(client, admin, code):
    return next(m for m in client.get("/api/admin/materials", headers=admin).json() if m["code"] == code)


def _carton(client, admin, code):
    return next(c for c in client.get("/api/admin/cartons", headers=admin).json() if c["code"] == code)


def _recommend(client, worker, order_id):
    r = client.post(f"/api/packwise/orders/{order_id}/recommend", headers=worker)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- C++ service directly
def test_cpp_service_health_and_validation(packer_url):
    h = httpx.get(packer_url + "/health").json()
    assert h["status"] == "ok" and h["capabilities"]["stacking"] is False
    bad = httpx.post(packer_url + "/v1/pack/cartons", content="{nope")
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "malformed_json"
    bad = httpx.post(packer_url + "/v1/pack/cartons",
                     json={"items": [{"id": "a", "l": -1, "w": 1, "h": 1}], "cartons": [{"id": "c", "l": 1, "w": 1, "h": 1}]})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_dimension"
    bad = httpx.post(packer_url + "/v1/pack/cartons",
                     json={"items": [{"id": "a", "l": 1.5, "w": 1, "h": 1}], "cartons": [{"id": "c", "l": 1, "w": 1, "h": 1}]})
    assert bad.status_code == 400
    ok = httpx.post(packer_url + "/v1/pack/cartons",
                    json={"items": [{"id": "a", "l": 50, "w": 40, "h": 30}], "cartons": [{"id": "c", "l": 100, "w": 100, "h": 100}]})
    res = ok.json()["results"][0]
    assert res["fits"] and res["placements"][0]["z"] == 0


def test_backend_reports_packer_health(app_client):
    assert app_client.get("/api/health/packer").json()["status"] == "ok"


def test_packer_unavailable_gives_meaningful_error(app_client, worker, place_order, monkeypatch):
    from app.config import settings
    order = place_order({"velvet-matte-lipstick": 1})
    monkeypatch.setattr(settings, "packer_url", "http://127.0.0.1:1")
    r = app_client.post(f"/api/packwise/orders/{order['id']}/recommend", headers=worker)
    assert r.status_code == 503 and "offline" in r.json()["detail"]
    assert app_client.get("/api/health/packer").status_code == 503


# ---------------------------------------------------------------- feasibility
@pytest.mark.usefixtures("original_algorithm")
def test_demo_order_recommendation(app_client, worker, place_order):
    order = place_order(DEMO)
    plan = _recommend(app_client, worker, order["id"])
    assert plan["status"] == "recommended"
    # Padded perfume and remover are 140 mm tall and stay upright: only the 150 mm and 200 mm tall
    # standard cartons can hold them; the smaller of the two wins.
    assert plan["carton"]["code"] == "STD-06"
    assert plan["carton"]["dims_mm"] == [360, 250, 150] and plan["carton"]["nominal_mm"] == [360, 250, 150]
    status = {e["carton"]["code"]: e for e in plan["evaluations"]}
    assert len(status) == 8
    for code in ("STD-01", "STD-02", "STD-03", "STD-04", "STD-05", "STD-08"):
        assert status[code]["status"] == "rejected" and any("taller" in r for r in status[code]["reasons"])
    assert status["STD-07"]["status"] == "feasible"
    feasible = [e for e in plan["evaluations"] if e["status"] == "feasible"]
    assert plan["carton"]["volume_cm3"] == min(e["carton"]["volume_cm3"] for e in feasible)
    assert plan["selected"]["why"][0].startswith("Smallest of the 8 warehouse cartons")
    # honest warnings: nominal size used as internal size, and no weight limit configured
    w = " ".join(plan["selected"]["warnings"])
    assert "not verified" in w and "No maximum weight" in w
    weight = next(ch for ch in plan["selected"]["checks"] if ch["name"] == "weight")
    assert weight["ok"] and weight["not_checked"]
    search = plan["selected"]["placement"]["search"]
    assert search["widths_tried"] == 400 and search["widths_that_fit"] >= 1
    # placements are the engine's, one per physical unit, all on the floor, inside the carton, no overlap
    pl = plan["placements"]
    assert len(pl) == 5 and all(p["z"] == 0 for p in pl)
    L, W, H = plan["carton"]["dims_cm"]
    for p in pl:
        assert p["x"] + p["dx"] <= L + 1e-9 and p["y"] + p["dy"] <= W + 1e-9 and p["dz"] <= H
    for i, a in enumerate(pl):
        for b in pl[i + 1:]:
            assert (a["x"] + a["dx"] <= b["x"] or b["x"] + b["dx"] <= a["x"] or
                    a["y"] + a["dy"] <= b["y"] or b["y"] + b["dy"] <= a["y"])
    # fragile perfume is padded and needs bubble wrap; remover needs a poly bag
    perfume = next(u for u in plan["units"] if u["name"].startswith("Rose Oud"))
    assert perfume["padding_cm"] >= 1.0 and perfume["padded_cm"] == [10.0, 7.0, 14.0]
    codes = {m["code"]: m for m in plan["selected"]["materials"]}
    assert codes["BUBBLE"]["quantity"] == 1 and codes["POLYBAG"]["quantity"] == 1 and codes["KRAFT"]["estimate"]
    # cost & baseline
    carton_price = plan["carton"]["unit_cost"]
    assert "unit_cost" in plan["carton"]["sample_fields"]          # sample price, flagged as such
    assert plan["estimated_cost"] == round(carton_price + 4 + 2 + codes["KRAFT"]["quantity"] * 1.5, 2)
    # the engine's raw JSON is kept with the plan
    assert len(plan["engine"]["response_results"]) >= 2
    assert plan["baseline"]["available"] is True
    assert plan["estimated_savings"] == round(plan["baseline_cost"] - plan["estimated_cost"], 2)


@pytest.mark.usefixtures("original_algorithm")
def test_padding_aware_feasibility(app_client, worker, admin, place_order):
    # Perfume padded = 100 x 70 x 140 mm. A 135 mm tall carton fits it only without padding.
    r = app_client.post("/api/admin/cartons", headers=admin, json={
        "code": "TIGHT", "name": "Tight", "nominal_length_mm": 90, "nominal_width_mm": 60, "nominal_height_mm": 135,
        "max_weight_g": 5000, "unit_cost": 1, "stock": 10})
    assert r.status_code == 201, r.text
    order = place_order({"rose-oud-eau-de-parfum": 1})
    plan = _recommend(app_client, worker, order["id"])
    tight = next(e for e in plan["evaluations"] if e["carton"]["code"] == "TIGHT")
    assert tight["status"] == "rejected"
    assert any("1.0 cm padding" in r for r in tight["reasons"])


@pytest.mark.usefixtures("original_algorithm")
def test_fragile_min_padding_applied(app_client, worker, place_order):
    # Highlighter has 0.5 cm padding in metadata but is fragile -> raised to the 1.0 cm fragile minimum
    plan = _recommend(app_client, worker, place_order({"satin-glow-highlighter": 1})["id"])
    u = plan["units"][0]
    assert u["padding_cm"] == 1.0 and u["padding_rule"] == "fragile_minimum"


def test_fragile_without_protection_blocks(app_client, worker, admin, place_order):
    pid = app_client.get("/api/products/stoneware-coffee-mug").json()["id"]
    app_client.patch(f"/api/admin/products/{pid}", json={"protection_material_code": ""}, headers=admin)
    plan = _recommend(app_client, worker, place_order({"stoneware-coffee-mug": 1})["id"])
    assert plan["status"] == "no_fit"
    assert any("no protective material" in b for b in plan["blockers"])


def test_weight_limit(app_client, worker, admin, place_order):
    for code in ("STD-06", "STD-07"):
        cid = _carton_id(app_client, admin, code)
        assert app_client.patch(f"/api/admin/cartons/{cid}", json={"max_weight_g": 100}, headers=admin).status_code == 200
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    assert plan["status"] == "no_fit"
    large = next(e for e in plan["evaluations"] if e["carton"]["code"] == "STD-06")
    assert any("carton limit" in r for r in large["reasons"])


def test_tall_item_goes_in_the_tallest_carton(app_client, worker, place_order):
    # Bud vase: 160 mm + 2 x 15 mm padding = 190 mm; only the Large Multi-Item Box (200 mm) is tall enough
    plan = _recommend(app_client, worker, place_order({"ceramic-bud-vase": 1})["id"])
    assert plan["carton"]["code"] == "STD-07"


@pytest.mark.usefixtures("original_algorithm")
def test_no_fit_for_tall_item_explains_alternatives(app_client, worker, place_order):
    # Reed diffuser: 220 mm + 2 x 10 mm padding = 240 mm, taller than every standard carton (max 200 mm)
    plan = _recommend(app_client, worker, place_order({"cedar-reed-diffuser": 1})["id"])
    assert plan["status"] == "no_fit" and plan["carton"] is None
    assert all(e["status"] != "feasible" for e in plan["evaluations"])
    alt = plan["alternatives"]
    assert alt and alt[0]["kind"] == "taller_carton" and "240 mm" in alt[0]["text"] and "200 mm" in alt[0]["text"]
    assert app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker).status_code == 409


@pytest.mark.usefixtures("original_algorithm")
def test_engine_rejects_floor_overflow(app_client, worker, place_order):
    # 12 notebooks: each fits a floor alone, but the single-layer engine cannot place 12 side by side
    plan = _recommend(app_client, worker, place_order({"dot-grid-notebook": 12})["id"])
    assert plan["status"] == "no_fit"
    xl = next(e for e in plan["evaluations"] if e["carton"]["code"] == "STD-07")
    assert any(r.startswith("Packing engine") for r in xl["reasons"])
    assert any(a["kind"] == "split" for a in plan["alternatives"])


def test_out_of_stock_carton_is_skipped(app_client, worker, admin, place_order):
    cid = _carton_id(app_client, admin, "STD-06")
    c = _carton(app_client, admin, "STD-06")
    app_client.post(f"/api/admin/cartons/{cid}/adjust", json={"delta": -c["stock"], "reason": "count"}, headers=admin)
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    assert plan["carton"]["code"] == "STD-07"          # next size that fits
    m = next(e for e in plan["evaluations"] if e["carton"]["code"] == "STD-06")
    assert any("No Medium Apparel / Electronics cartons available" in r for r in m["reasons"])
    assert any("Medium Apparel / Electronics (out of stock)" in w for w in plan["selected"]["why"])


def test_material_shortage_blocks(app_client, worker, admin, place_order):
    m = _material(app_client, admin, "BUBBLE")
    app_client.post(f"/api/admin/materials/{m['id']}/adjust", json={"delta": -m["stock"], "reason": "count"},
                    headers=admin)
    plan = _recommend(app_client, worker, place_order({"rose-oud-eau-de-parfum": 1})["id"])
    assert plan["status"] == "no_fit"


def test_missing_cost_data(app_client, worker, admin, place_order):
    for code in ("STD-07",):
        cid = _carton_id(app_client, admin, code)
        app_client.patch(f"/api/admin/cartons/{cid}", json={"clear_unit_cost": True}, headers=admin)
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    assert plan["baseline"]["available"] is False and "missing" in plan["baseline"]["reason"]
    assert plan["estimated_savings"] is None and plan["estimated_cost"] is not None


# ---------------------------------------------------------------- reservations
def test_accept_reserves_and_cancel_releases(app_client, worker, admin, place_order):
    order = place_order(DEMO)
    plan = _recommend(app_client, worker, order["id"])
    before = _carton(app_client, admin, "STD-06")
    r = app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker)
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    after = _carton(app_client, admin, "STD-06")
    assert after["reserved"] == before["reserved"] + 1 and after["stock"] == before["stock"]
    assert app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker).status_code == 409
    assert app_client.get(f"/api/orders/{order['code']}", headers=None).status_code == 401
    r = app_client.post(f"/api/packwise/plans/{plan['id']}/cancel", json={"reason": "wrong bench"}, headers=worker)
    assert r.json()["status"] == "cancelled"
    assert _carton(app_client, admin, "STD-06")["reserved"] == before["reserved"]
    # cancelling twice is refused
    assert app_client.post(f"/api/packwise/plans/{plan['id']}/cancel", json={"reason": "again"},
                           headers=worker).status_code == 409


def test_cannot_reserve_unavailable_stock(app_client, worker, admin, place_order):
    # Only one Medium Apparel carton exists; two orders compete for it.
    c = _carton(app_client, admin, "STD-06")
    app_client.post(f"/api/admin/cartons/{c['id']}/adjust", json={"delta": 1 - c["stock"], "reason": "test"},
                    headers=admin)
    p1 = _recommend(app_client, worker, place_order(DEMO)["id"])
    p2 = _recommend(app_client, worker, place_order(DEMO)["id"])
    assert p1["carton"]["code"] == p2["carton"]["code"] == "STD-06"
    assert app_client.post(f"/api/packwise/plans/{p1['id']}/accept", headers=worker).status_code == 200
    r = app_client.post(f"/api/packwise/plans/{p2['id']}/accept", headers=worker)
    assert r.status_code == 409 and "Not enough" in r.json()["detail"]
    assert _carton(app_client, admin, "STD-06")["reserved"] == 1
    # and the failed plan is still re-acceptable once stock returns
    assert app_client.get(f"/api/packwise/plans/{p2['id']}", headers=worker).json()["status"] == "recommended"


def test_concurrent_accepts_reserve_once(app_client, worker, admin, place_order):
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    before = _carton(app_client, admin, "STD-06")["reserved"]
    codes = []

    def go():
        codes.append(app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker).status_code)

    threads = [threading.Thread(target=go) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes.count(200) == 1 and codes.count(409) == 4
    assert _carton(app_client, admin, "STD-06")["reserved"] == before + 1


def test_catalogue_change_forces_new_recommendation(app_client, worker, admin, place_order):
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    cid = _carton_id(app_client, admin, "STD-06")
    app_client.patch(f"/api/admin/cartons/{cid}", json={"height_mm": 145}, headers=admin)
    r = app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker)
    assert r.status_code == 409 and "changed" in r.json()["detail"]


# ---------------------------------------------------------------- completion
def test_complete_consumes_exactly_once(app_client, worker, admin, customer, place_order):
    order = place_order(DEMO)
    plan = _recommend(app_client, worker, order["id"])
    app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker)
    c0, b0, k0 = _carton(app_client, admin, "STD-06"), _material(app_client, admin, "BUBBLE"), _material(app_client, admin, "KRAFT")
    kraft_reserved = next(m["quantity"] for m in plan["selected"]["materials"] if m["code"] == "KRAFT")

    incomplete = app_client.post(f"/api/packwise/plans/{plan['id']}/complete", headers=worker,
                                 json={"checklist": {"items_match_order": True}})
    assert incomplete.status_code == 422

    body = {"checklist": FULL_CHECKLIST, "materials_used": [{"code": "KRAFT", "quantity": kraft_reserved + 1}]}
    r1 = app_client.post(f"/api/packwise/plans/{plan['id']}/complete", headers=worker, json=body)
    assert r1.status_code == 200 and r1.json()["already_completed"] is False
    r2 = app_client.post(f"/api/packwise/plans/{plan['id']}/complete", headers=worker, json=body)
    assert r2.status_code == 200 and r2.json()["already_completed"] is True

    c1, b1, k1 = _carton(app_client, admin, "STD-06"), _material(app_client, admin, "BUBBLE"), _material(app_client, admin, "KRAFT")
    assert c1["stock"] == c0["stock"] - 1 and c1["reserved"] == c0["reserved"] - 1
    assert b1["stock"] == b0["stock"] - 1 and b1["reserved"] == b0["reserved"] - 1
    assert k1["stock"] == k0["stock"] - (kraft_reserved + 1) and k1["reserved"] == k0["reserved"] - kraft_reserved
    # actual cost reflects the extra kraft sheet
    assert r1.json()["actual_cost"] == round(plan["estimated_cost"] + 1.5, 2)
    # customer sees the new status
    tracked = app_client.get(f"/api/orders/{order['code']}", headers=customer).json()
    assert tracked["status"] == "packed"
    # dispatch flow
    assert app_client.post(f"/api/packwise/orders/{order['id']}/dispatch", json={"status": "dispatched"},
                           headers=worker).status_code == 409
    assert app_client.post(f"/api/packwise/orders/{order['id']}/dispatch", json={"status": "ready_for_dispatch"},
                           headers=worker).status_code == 200
    # movements explain the change
    moves = app_client.get("/api/admin/movements", params={"item_type": "carton", "item_id": c1["id"]},
                           headers=admin).json()
    kinds = [m["kind"] for m in moves]
    assert kinds.count("consume") == 1 and "reserve" in kinds


def test_complete_requires_protection_material(app_client, worker, place_order):
    plan = _recommend(app_client, worker, place_order({"rose-oud-eau-de-parfum": 1})["id"])
    app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker)
    r = app_client.post(f"/api/packwise/plans/{plan['id']}/complete", headers=worker,
                        json={"checklist": FULL_CHECKLIST, "materials_used": [{"code": "BUBBLE", "quantity": 0}]})
    assert r.status_code == 422


# ---------------------------------------------------------------- overrides
def test_override_rules(app_client, worker, admin, place_order):
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    small, xl = _carton_id(app_client, admin, "STD-01"), _carton_id(app_client, admin, "STD-07")
    # reason is mandatory
    assert app_client.post(f"/api/packwise/plans/{plan['id']}/override", headers=worker,
                           json={"carton_id": xl, "reason": ""}).status_code == 422
    # unsafe carton rejected with reasons
    r = app_client.post(f"/api/packwise/plans/{plan['id']}/override", headers=worker,
                        json={"carton_id": small, "reason": "Trying the small box first"})
    assert r.status_code == 422 and r.json()["detail"]["reasons"]
    # valid override creates a new plan and keeps the original recommendation
    r = app_client.post(f"/api/packwise/plans/{plan['id']}/override", headers=worker,
                        json={"carton_id": xl, "reason": "Large cartons on this bench are damaged"})
    assert r.status_code == 200
    new = r.json()
    assert new["is_override"] and new["carton"]["code"] == "STD-07"
    assert new["override"]["original_carton"] == "STD-06" and new["override"]["reason"].startswith("Large")
    assert new["estimated_savings"] == 0.0  # STD-07 is the baseline itself
    old = app_client.get(f"/api/packwise/plans/{plan['id']}", headers=worker).json()
    assert old["status"] == "superseded"
    ov = app_client.get("/api/admin/overrides", headers=admin).json()
    assert ov[0]["from"] == "STD-06" and ov[0]["to"] == "STD-07" and ov[0]["actor"] == "worker:Tester"


def test_override_of_accepted_plan_releases_stock(app_client, worker, admin, place_order):
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker)
    reserved = _carton(app_client, admin, "STD-06")["reserved"]
    xl = _carton_id(app_client, admin, "STD-07")
    app_client.post(f"/api/packwise/plans/{plan['id']}/override", headers=worker,
                    json={"carton_id": xl, "reason": "Customer requested gift box size"})
    assert _carton(app_client, admin, "STD-06")["reserved"] == reserved - 1


# ---------------------------------------------------------------- history & reports
def test_snapshot_survives_catalogue_edits_and_no_double_counting(app_client, worker, admin, place_order):
    order = place_order(DEMO)
    _recommend(app_client, worker, order["id"])                # first try
    plan = _recommend(app_client, worker, order["id"])         # regenerated: first is superseded
    app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker)
    app_client.post(f"/api/packwise/plans/{plan['id']}/complete", headers=worker, json={"checklist": FULL_CHECKLIST})
    app_client.post(f"/api/packwise/plans/{plan['id']}/complete", headers=worker, json={"checklist": FULL_CHECKLIST})

    cid = _carton_id(app_client, admin, "STD-06")
    app_client.patch(f"/api/admin/cartons/{cid}", json={"unit_cost": 999, "height_mm": 160}, headers=admin)

    rep = app_client.get("/api/admin/reports", headers=admin).json()
    assert rep["totals"]["orders"] == 1
    row = rep["rows"][0]
    assert row["actual_cost"] == plan["estimated_cost"]        # old price kept
    assert row["savings"] == plan["estimated_savings"]
    stored = app_client.get(f"/api/packwise/plans/{plan['id']}", headers=worker).json()
    assert stored["carton"]["dims_cm"] == [36, 25, 15] and stored["carton"]["unit_cost"] == plan["carton"]["unit_cost"]

    dash = app_client.get("/api/admin/dashboard", headers=admin).json()
    assert dash["completed"]["count"] == 1
    assert dash["completed"]["savings_total"] == plan["estimated_savings"]
    assert dash["completed"]["actual_cost_total"] == plan["estimated_cost"]
    assert dash["pending"]["plans"] == 0

    hist = app_client.get("/api/admin/history", params={"q": order["code"]}, headers=admin).json()
    assert {h["status"] for h in hist} == {"superseded", "completed"}
    assert app_client.get("/api/admin/history", params={"status": "completed"}, headers=admin).json()[0]["id"] == plan["id"]


def test_dashboard_counts_and_low_stock(app_client, worker, admin, place_order):
    place_order({"velvet-matte-lipstick": 1})
    fragile = place_order({"rose-oud-eau-de-parfum": 1})
    app_client.post(f"/api/admin/orders/{fragile['id']}/priority", json={"priority": True, "reason": "VIP"},
                    headers=admin)
    m = _material(app_client, admin, "FOAM")
    app_client.post(f"/api/admin/materials/{m['id']}/adjust", json={"delta": -(m['stock'] - 5), "reason": "count"},
                    headers=admin)
    d = app_client.get("/api/admin/dashboard", headers=admin).json()
    assert d["orders"]["awaiting_packing"] == 2 and d["orders"]["awaiting_recommendation"] == 2
    assert d["orders"]["fragile_open"] == 1 and d["orders"]["priority_open"] == 1
    assert any(a["code"] == "FOAM" for a in d["low_stock"])
    assert d["completed"]["count"] == 0 and d["completed"]["savings_total"] is None
    queue = app_client.get("/api/packwise/orders", headers=worker).json()
    assert queue[0]["id"] == fragile["id"]   # priority first


def test_worker_cannot_use_admin_routes(app_client, worker):
    assert app_client.get("/api/admin/dashboard", headers=worker).status_code == 403
    assert app_client.post("/api/auth/worker", json={"code": "WRONG", "worker_name": "Eve"}).status_code == 401


def test_stock_cannot_drop_below_reserved(app_client, worker, admin, place_order):
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker)
    c = _carton(app_client, admin, "STD-06")
    r = app_client.post(f"/api/admin/cartons/{c['id']}/adjust", json={"delta": -c["stock"], "reason": "stock count"},
                        headers=admin)
    assert r.status_code == 409
