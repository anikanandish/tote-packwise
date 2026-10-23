"""The eight standard cartons (mm), admin carton management and the upgrade of older databases."""
import sqlite3

from conftest import DEMO

STANDARD = {
    "STD-01": ("Ultra-Small / Cosmetics", [100, 100, 50]),
    "STD-02": ("Small Mailer / Accessories", [200, 150, 100]),
    "STD-03": ("Medium Mailer / Skincare Kit", [230, 150, 100]),
    "STD-04": ("Standard E-commerce Box", [300, 230, 100]),
    "STD-05": ("Shoe Box / Small Gadgets", [300, 200, 130]),
    "STD-06": ("Medium Apparel / Electronics", [360, 250, 150]),
    "STD-07": ("Large Multi-Item Box", [460, 360, 200]),
    "STD-08": ("Heavy Gadget Carrier", [290, 280, 130]),
}


def _cartons(client, admin):
    return {c["code"]: c for c in client.get("/api/admin/cartons", headers=admin).json()}


def _recommend(client, worker, order_id):
    r = client.post(f"/api/packwise/orders/{order_id}/recommend", headers=worker)
    assert r.status_code == 200, r.text
    return r.json()


def test_eight_standard_cartons_exact(app_client, admin):
    c = _cartons(app_client, admin)
    std = {k: v for k, v in c.items() if v["is_predefined"]}
    assert set(std) == set(STANDARD)
    for code, (name, dims) in STANDARD.items():
        row = std[code]
        assert row["name"] == name and row["nominal_mm"] == dims and row["internal_mm"] == dims
        assert row["internal_verified"] is False and row["max_weight_g"] is None      # nothing invented
        assert row["volume_cm3"] == dims[0] * dims[1] * dims[2] / 1000                # calculated
        assert set(row["sample_fields"]) == {"unit_cost", "stock", "min_stock"}        # flagged sample values
    assert [k for k, v in c.items() if v["is_baseline"]] == ["STD-07"]


def test_seed_is_idempotent_and_keeps_admin_edits(app_client, admin):
    from app import database
    from app.seed import seed
    cid = _cartons(app_client, admin)["STD-03"]["id"]
    app_client.patch(f"/api/admin/cartons/{cid}", json={"min_stock": 3, "length_mm": 226}, headers=admin)
    db = database.SessionLocal()
    try:
        seed(db)
        seed(db)
    finally:
        db.close()
    c = _cartons(app_client, admin)
    assert sum(1 for v in c.values() if v["is_predefined"]) == 8
    assert c["STD-03"]["min_stock"] == 3 and c["STD-03"]["internal_mm"] == [226, 150, 100]
    assert c["STD-03"]["nominal_mm"] == [230, 150, 100]
    assert "min_stock" not in c["STD-03"]["sample_fields"] and "unit_cost" in c["STD-03"]["sample_fields"]


def test_fit_uses_internal_dimensions(app_client, worker, admin, place_order):
    # Measure STD-06 as 145 mm high inside: the 140 mm items still fit; at 139 mm they do not.
    cid = _cartons(app_client, admin)["STD-06"]["id"]
    app_client.patch(f"/api/admin/cartons/{cid}", json={"height_mm": 139, "internal_verified": True}, headers=admin)
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    assert plan["carton"]["code"] == "STD-07"
    std6 = next(e for e in plan["evaluations"] if e["carton"]["code"] == "STD-06")
    assert std6["carton"]["dims_mm"] == [360, 250, 139] and std6["carton"]["nominal_mm"] == [360, 250, 150]
    assert any("taller" in r for r in std6["reasons"])


def test_smallest_wins_even_if_a_bigger_box_is_cheaper(app_client, worker, admin, place_order):
    big = _cartons(app_client, admin)["STD-07"]["id"]
    app_client.patch(f"/api/admin/cartons/{big}", json={"unit_cost": 1}, headers=admin)
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    assert plan["carton"]["code"] == "STD-06"


def test_small_order_uses_a_small_mailer(app_client, worker, place_order):
    # Lipstick 25 x 25 x 85 mm: the 50 mm Ultra-Small box is too short; the Small Mailer fits.
    plan = _recommend(app_client, worker, place_order({"velvet-matte-lipstick": 1})["id"])
    assert plan["carton"]["code"] == "STD-02"
    L, W, H = plan["carton"]["dims_cm"]
    for p in plan["placements"]:
        assert p["x"] + p["dx"] <= L + 1e-9 and p["y"] + p["dy"] <= W + 1e-9 and p["dz"] <= H


def test_add_custom_carton_validation_and_use(app_client, worker, admin, place_order):
    bad = app_client.post("/api/admin/cartons", headers=admin, json={
        "code": "X1", "name": "Bad", "nominal_length_mm": -5, "nominal_width_mm": 100, "nominal_height_mm": 100})
    assert bad.status_code == 422
    bad = app_client.post("/api/admin/cartons", headers=admin, json={
        "code": "X1", "name": "Bad", "nominal_length_mm": 100, "nominal_width_mm": 100, "nominal_height_mm": 100,
        "stock": -1})
    assert bad.status_code == 422
    r = app_client.post("/api/admin/cartons", headers=admin, json={
        "code": "LIP-BOX", "name": "Lipstick sleeve", "nominal_length_mm": 40, "nominal_width_mm": 40,
        "nominal_height_mm": 95, "length_mm": 36, "width_mm": 36, "height_mm": 92, "internal_verified": True,
        "max_weight_g": 500, "unit_cost": 3.5, "stock": 20})
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["is_predefined"] is False and row["sample_fields"] == [] and row["internal_mm"] == [36, 36, 92]
    assert app_client.post("/api/admin/cartons", headers=admin, json={
        "code": "LIP-BOX", "name": "Dup", "nominal_length_mm": 1, "nominal_width_mm": 1,
        "nominal_height_mm": 1}).status_code == 409
    plan = _recommend(app_client, worker, place_order({"velvet-matte-lipstick": 1})["id"])
    assert plan["carton"]["code"] == "LIP-BOX"     # smaller than any standard carton that fits
    assert plan["selected"]["warnings"] == []      # verified size and a weight limit: nothing to warn about
    # used in a plan -> cannot be deleted, only deactivated
    d = app_client.delete(f"/api/admin/cartons/{row['id']}", headers=admin)
    assert d.status_code == 409 and "Deactivate" in d.json()["detail"]
    assert app_client.patch(f"/api/admin/cartons/{row['id']}", json={"is_active": False},
                            headers=admin).json()["is_active"] is False


def test_unused_custom_carton_can_be_deleted_but_standard_cannot(app_client, admin):
    r = app_client.post("/api/admin/cartons", headers=admin, json={
        "code": "TEMP", "name": "Temporary", "nominal_length_mm": 100, "nominal_width_mm": 100, "nominal_height_mm": 100})
    assert app_client.delete(f"/api/admin/cartons/{r.json()['id']}", headers=admin).json() == {"ok": True}
    std = _cartons(app_client, admin)["STD-01"]["id"]
    assert app_client.delete(f"/api/admin/cartons/{std}", headers=admin).status_code == 409


def test_deactivation_and_resize_blocked_while_reserved(app_client, worker, admin, place_order):
    plan = _recommend(app_client, worker, place_order(DEMO)["id"])
    assert app_client.post(f"/api/packwise/plans/{plan['id']}/accept", headers=worker).status_code == 200
    cid = _cartons(app_client, admin)["STD-06"]["id"]
    r = app_client.patch(f"/api/admin/cartons/{cid}", json={"is_active": False}, headers=admin)
    assert r.status_code == 409 and "reserved" in r.json()["detail"]
    r = app_client.patch(f"/api/admin/cartons/{cid}", json={"height_mm": 120}, headers=admin)
    assert r.status_code == 409
    # cost and threshold edits are fine; the plan keeps its frozen price
    assert app_client.patch(f"/api/admin/cartons/{cid}", json={"unit_cost": 70}, headers=admin).status_code == 200
    base = _cartons(app_client, admin)["STD-07"]["id"]
    assert app_client.patch(f"/api/admin/cartons/{base}", json={"is_active": False}, headers=admin).status_code == 409


def test_baseline_can_move_but_never_disappear(app_client, admin):
    c = _cartons(app_client, admin)
    assert app_client.patch(f"/api/admin/cartons/{c['STD-07']['id']}", json={"is_baseline": False},
                            headers=admin).status_code == 409
    assert app_client.patch(f"/api/admin/cartons/{c['STD-06']['id']}", json={"is_baseline": True},
                            headers=admin).status_code == 200
    c = _cartons(app_client, admin)
    assert [k for k, v in c.items() if v["is_baseline"]] == ["STD-06"]


def test_stock_adjust_clears_sample_flag(app_client, admin):
    c = _cartons(app_client, admin)["STD-02"]
    r = app_client.post(f"/api/admin/cartons/{c['id']}/adjust", json={"delta": 10, "reason": "Counted on shelf"},
                        headers=admin)
    assert r.json()["stock"] == c["stock"] + 10 and "stock" not in r.json()["sample_fields"]


def test_upgrade_from_centimetre_schema(tmp_path):
    """An old (v7) database: cartons in cm, a plan pointing at one. Migration keeps ids and history."""
    from app import database, migrate
    from app.main import init_db
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE cartons (id INTEGER PRIMARY KEY, code VARCHAR(40) UNIQUE, name VARCHAR(80), length_cm FLOAT,
            width_cm FLOAT, height_cm FLOAT, max_weight_g INTEGER NOT NULL, unit_cost FLOAT, stock INTEGER,
            reserved INTEGER, min_stock INTEGER, is_active BOOLEAN, is_baseline BOOLEAN, notes TEXT, updated_at DATETIME);
        CREATE TABLE ref (id INTEGER PRIMARY KEY, carton_id INTEGER REFERENCES cartons(id));
        INSERT INTO cartons VALUES (7, 'BOX-2', 'Small', 20, 14, 15, 3000, 14, 139, 0, 25, 1, 0, '', '2026-10-23');
        INSERT INTO cartons VALUES (9, 'BOX-6', 'Large', 40, 30, 26, 15000, 42, 50, 0, 8, 1, 1, '', '2026-10-23');
        INSERT INTO ref VALUES (1, 9);
    """)
    con.commit()
    con.close()
    database.configure(f"sqlite:///{path.as_posix()}")
    init_db()
    assert migrate.run(database.engine) == []          # second run: nothing to do
    con = sqlite3.connect(path)
    rows = {r[0]: r for r in con.execute(
        "SELECT code, id, length_mm, width_mm, height_mm, nominal_length_mm, is_active, is_baseline, max_weight_g, stock "
        "FROM cartons")}
    assert rows["BOX-6"][1:6] == (9, 400, 300, 260, 400) and rows["BOX-6"][8] == 15000 and rows["BOX-6"][9] == 50
    assert rows["BOX-2"][6] == 0 and rows["BOX-6"][6] == 0 and rows["BOX-6"][7] == 0      # retired once
    assert rows["STD-07"][7] == 1                                                          # new baseline
    assert con.execute("SELECT carton_id FROM ref").fetchone() == (9,)                     # reference intact
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()
