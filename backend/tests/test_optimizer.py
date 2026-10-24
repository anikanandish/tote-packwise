"""The new optimizer (cpp-packer-service/original/optimizer.cpp) choosing among the warehouse cartons."""
import httpx
import pytest

from conftest import DEMO


def _recommend(client, worker, order_id):
    r = client.post(f"/api/packwise/orders/{order_id}/recommend", headers=worker)
    assert r.status_code == 200, r.text
    return r.json()


def _inside_and_apart(plan):
    L, W, H = plan["carton"]["dims_cm"]
    pl = plan["placements"]
    for p in pl:
        assert p["x"] >= 0 and p["y"] >= 0 and p["z"] >= 0
        assert p["x"] + p["dx"] <= L + 1e-9 and p["y"] + p["dy"] <= W + 1e-9 and p["z"] + p["dz"] <= H + 1e-9
    for i, a in enumerate(pl):
        for b in pl[i + 1:]:
            assert (a["x"] + a["dx"] <= b["x"] or b["x"] + b["dx"] <= a["x"] or
                    a["y"] + a["dy"] <= b["y"] or b["y"] + b["dy"] <= a["y"] or
                    a["z"] + a["dz"] <= b["z"] or b["z"] + b["dz"] <= a["z"])


def test_engine_optimizer_mode_directly(packer_url):
    body = {"algorithm": "optimizer",
            "items": [{"id": "a", "l": 100, "w": 100, "h": 40}, {"id": "b", "l": 100, "w": 100, "h": 40},
                      {"id": "c", "l": 100, "w": 100, "h": 40}, {"id": "d", "l": 40, "w": 40, "h": 40, "fragile": True}],
            "cartons": [{"id": "C1", "l": 200, "w": 100, "h": 120}]}
    r = httpx.post(packer_url + "/v1/pack/cartons", json=body).json()
    assert r["algorithm"] == "optimizer"
    res = r["results"][0]
    assert res["fits"]
    z = [p["z"] for p in res["placements"]]
    assert max(z) > 0                                   # the floor holds two, so it stacks
    frag = next(p for p in res["placements"] if p["id"] == "d")
    assert (frag["dx"], frag["dy"], frag["dz"]) == (70, 70, 70) and frag["cushion_mm"] == 15
    assert all(a["widths_tried"] <= 60 for a in res["attempts"])
    bad = httpx.post(packer_url + "/v1/pack/cartons", json={**body, "algorithm": "magic"})
    assert bad.status_code == 400
    # without "algorithm" the original packer.cpp answers, as before
    assert httpx.post(packer_url + "/v1/pack/cartons", json={k: v for k, v in body.items() if k != "algorithm"}
                      ).json()["algorithm"] == "original"


@pytest.mark.usefixtures("layered_optimizer")
def test_demo_order_uses_optimizer(app_client, worker, place_order):
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    assert plan["status"] == "recommended"
    assert plan["engine"]["request"]["algorithm"] == "optimizer"
    assert plan["engine"]["response_meta"]["algorithm"] == "optimizer"
    sent = {i["id"]: i for i in plan["engine"]["request"]["items"]}
    perfume = next(u for u in plan["units"] if u["name"].startswith("Rose Oud"))
    # fragile: sent bare with fragile=true; the optimizer adds its own 15 mm cushion on every side
    assert sent[perfume["ref"]] == {"id": perfume["ref"], "l": 80, "w": 50, "h": 120, "fragile": True}
    assert perfume["padding_cm"] == 1.5 and perfume["padding_rule"] == "optimizer_fragile_cushion"
    assert perfume["padded_mm"] == [110, 80, 150]
    # non-fragile items keep their product padding and are sent padded
    remover = next(u for u in plan["units"] if u["name"].startswith("Gentle"))
    assert sent[remover["ref"]] == {"id": remover["ref"], "l": 70, "w": 50, "h": 140, "fragile": False}
    feasible = [e for e in plan["evaluations"] if e["status"] == "feasible"]
    assert plan["carton"]["volume_cm3"] == min(e["carton"]["volume_cm3"] for e in feasible)
    assert plan["selected"]["placement"]["search"]["widths_tried"] <= 120
    assert len(plan["placements"]) == 5
    _inside_and_apart(plan)
    assert plan["baseline"]["available"] is True


@pytest.mark.usefixtures("layered_optimizer")
def test_stacking_fits_what_one_layer_could_not(app_client, worker, place_order):
    # 12 notebooks do not fit side by side in any carton (see test_engine_rejects_floor_overflow);
    # the optimizer stacks them in layers.
    plan = _recommend(app_client, worker, place_order({"dot-grid-notebook": 12})["id"])
    assert plan["status"] == "recommended"
    assert any(p["z"] > 0 for p in plan["placements"])
    _inside_and_apart(plan)


@pytest.mark.usefixtures("layered_optimizer")
def test_tall_item_with_cushion_still_rejected(app_client, worker, place_order):
    # Reed diffuser 220 mm tall + 30 mm cushion = 250 mm; tallest carton is 200 mm
    plan = _recommend(app_client, worker, place_order({"cedar-reed-diffuser": 1})["id"])
    assert plan["status"] == "no_fit"
    assert any(a["kind"] == "taller_carton" and "250 mm" in a["text"] for a in plan["alternatives"])
