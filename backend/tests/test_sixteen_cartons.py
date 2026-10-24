"""16 standard cartons + the cushion optimizer (cpp-packer-service/original/optimizer2.cpp), the default."""
import httpx
import pytest

from conftest import DEMO

pytestmark = pytest.mark.sixteen_cartons

SIXTEEN = {
    "STD-01": [100, 100, 50], "STD-02": [200, 150, 100], "STD-03": [230, 150, 100], "STD-04": [300, 230, 100],
    "STD-05": [300, 200, 130], "STD-06": [360, 250, 150], "STD-07": [460, 360, 200], "STD-08": [290, 280, 130],
    "STD-09": [150, 100, 150], "STD-10": [250, 180, 50], "STD-11": [200, 150, 150], "STD-12": [320, 240, 60],
    "STD-13": [200, 200, 200], "STD-14": [120, 120, 250], "STD-15": [300, 200, 200], "STD-16": [400, 300, 100],
}


def _recommend(client, worker, order_id):
    r = client.post(f"/api/packwise/orders/{order_id}/recommend", headers=worker)
    assert r.status_code == 200, r.text
    return r.json()


def _inside_and_apart(plan):
    L, W, H = plan["carton"]["dims_cm"]
    pl = plan["placements"]
    for p in pl:
        assert p["z"] == 0                                    # one layer
        assert p["x"] + p["dx"] <= L + 1e-9 and p["y"] + p["dy"] <= W + 1e-9 and p["dz"] <= H + 1e-9
    for i, a in enumerate(pl):
        for b in pl[i + 1:]:
            assert (a["x"] + a["dx"] <= b["x"] or b["x"] + b["dx"] <= a["x"] or
                    a["y"] + a["dy"] <= b["y"] or b["y"] + b["dy"] <= a["y"])


def test_sixteen_standard_cartons(app_client, admin):
    rows = {c["code"]: c for c in app_client.get("/api/admin/cartons", headers=admin).json() if c["is_predefined"]}
    assert {k: v["nominal_mm"] for k, v in rows.items()} == SIXTEEN
    assert all("unit_cost" in v["sample_fields"] for v in rows.values())     # sample prices, flagged
    assert [c for c in rows.values() if c["is_baseline"]][0]["code"] == "STD-07"


def test_engine_optimizer2_mode_directly(packer_url):
    body = {"algorithm": "optimizer2",
            "items": [{"id": "a", "l": 100, "w": 70, "h": 125}, {"id": "f", "l": 80, "w": 50, "h": 120, "fragile": True}],
            "cartons": [{"id": "C1", "l": 360, "w": 250, "h": 150}, {"id": "C2", "l": 300, "w": 200, "h": 130}]}
    r = httpx.post(packer_url + "/v1/pack/cartons", json=body).json()
    assert r["algorithm"] == "optimizer2"
    c1, c2 = r["results"]
    assert c1["fits"] and not c2["fits"]                      # 120 + 15 mm cushion = 135 > 130
    f = next(p for p in c1["placements"] if p["id"] == "f")
    assert sorted([f["dx"], f["dy"]]) == [65, 95] and f["dz"] == 135 and f["z"] == 0 and f["cushion_mm"] == 7.5
    assert all(a["widths_tried"] == 200 for a in c1["attempts"])


def test_demo_order_with_optimizer2(app_client, worker, place_order):
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    assert plan["status"] == "recommended"
    assert plan["engine"]["request"]["algorithm"] == "optimizer2"
    assert plan["engine"]["response_meta"]["algorithm"] == "optimizer2"
    assert len(plan["evaluations"]) == 16
    perfume = next(u for u in plan["units"] if u["name"].startswith("Rose Oud"))
    assert perfume["padding_cm"] == 0.75 and perfume["padding_rule"] == "optimizer2_fragile_cushion"
    assert perfume["padded_mm"] == [95, 65, 135]
    feasible = [e for e in plan["evaluations"] if e["status"] == "feasible"]
    assert plan["carton"]["volume_cm3"] == min(e["carton"]["volume_cm3"] for e in feasible)
    assert plan["carton"]["volume_cm3"] < 13500           # smaller than the 8-carton answer (STD-06)
    _inside_and_apart(plan)
    assert plan["baseline"]["available"] and plan["estimated_savings"] > 0


def test_reed_diffuser_now_has_a_carton(app_client, worker, place_order):
    # 220 mm tall + 15 mm cushion = 235 mm: only the 250 mm Tall Vase / Diffuser Box holds it
    plan = _recommend(app_client, worker, place_order({"cedar-reed-diffuser": 1})["id"])
    assert plan["status"] == "recommended" and plan["carton"]["code"] == "STD-14"
    _inside_and_apart(plan)


# ---------------------------------------------------------------- made-to-measure (edge cases only)
@pytest.mark.made_to_measure
def test_close_fit_keeps_the_stock_carton(app_client, worker, place_order):
    # the demo order fits a stock carton well: no made-to-measure box
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    assert plan["carton"]["code"].startswith("STD-")


@pytest.mark.made_to_measure
def test_poor_fit_gets_a_made_to_measure_box(app_client, worker, place_order):
    # candle + notebook: best stock carton is 290 x 280 x 130 mm, far bigger than needed
    plan = _recommend(app_client, worker, place_order({"amber-soy-candle": 1, "dot-grid-notebook": 1})["id"])
    assert plan["status"] == "recommended"
    assert plan["carton"]["code"] == "MTM-BOX" and plan["carton"]["name"] == "Made-to-measure box"
    W, L, H = plan["carton"]["dims_mm"]
    best_stock = min(e["carton"]["volume_cm3"] for e in plan["evaluations"]
                     if e["status"] == "feasible" and e["carton"]["code"].startswith("STD-"))
    assert best_stock > 1.5 * W * L * H / 1000
    assert "unit_cost" in plan["carton"]["sample_fields"]
    _inside_and_apart(plan)
    # it can be accepted (stock reserved) like any carton
    acc = app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker)
    assert acc.status_code == 200, acc.text


@pytest.mark.made_to_measure
def test_no_stock_carton_fits_gets_a_made_to_measure_box(app_client, worker, admin, place_order):
    # switch off the only carton tall enough for the diffuser
    cid = next(c["id"] for c in app_client.get("/api/admin/cartons", headers=admin).json() if c["code"] == "STD-14")
    assert app_client.patch(f"/api/admin/cartons/{cid}", json={"is_active": False}, headers=admin).status_code == 200
    plan = _recommend(app_client, worker, place_order({"cedar-reed-diffuser": 1})["id"])
    assert plan["status"] == "recommended" and plan["carton"]["code"] == "MTM-BOX"
    assert plan["carton"]["dims_mm"][2] == 235            # 220 mm + 15 mm cushion
