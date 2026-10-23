"""Customer-facing behaviour: auth, catalogue, cart, checkout, tracking."""
from conftest import CHECKOUT, _auth


def test_register_login_and_password_is_hashed(app_client):
    r = app_client.post("/api/auth/register", json={"name": "Ravi", "email": "Ravi@Example.com", "password": "longpass1"})
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "ravi@example.com"
    assert app_client.post("/api/auth/register", json={"name": "Ravi", "email": "ravi@example.com",
                                                         "password": "longpass1"}).status_code == 409
    assert app_client.post("/api/auth/login", json={"email": "ravi@example.com", "password": "wrong"}).status_code == 401
    ok = app_client.post("/api/auth/login", json={"email": "ravi@example.com", "password": "longpass1"})
    assert ok.status_code == 200
    me = app_client.get("/api/auth/me", headers=_auth(ok.json()["token"]))
    assert me.json()["role"] == "customer"

    from app import database
    from app.models import User
    db = database.SessionLocal()
    u = db.query(User).filter(User.email == "ravi@example.com").one()
    assert "longpass1" not in u.password_hash and u.password_hash.startswith("pbkdf2_sha256$")
    db.close()


def test_short_password_rejected(app_client):
    r = app_client.post("/api/auth/register", json={"name": "A B", "email": "ab@example.com", "password": "short"})
    assert r.status_code == 422


def test_catalogue_search_filter_sort(app_client):
    all_items = app_client.get("/api/products").json()["items"]
    assert len(all_items) == 30
    q = app_client.get("/api/products", params={"q": "lipstick"}).json()["items"]
    assert [p["slug"] for p in q] == ["velvet-matte-lipstick"]
    beauty = app_client.get("/api/products", params={"category": "Beauty"}).json()["items"]
    assert beauty and all(p["category"] == "Beauty" for p in beauty)
    cheap = app_client.get("/api/products", params={"max_price": 800, "sort": "price_asc"}).json()["items"]
    prices = [p["price"] for p in cheap]
    assert prices == sorted(prices) and max(prices) <= 800
    detail = app_client.get("/api/products/rose-oud-eau-de-parfum").json()
    assert detail["packaging"]["fragile"] is True
    assert detail["reviews"] and all(r["is_demo"] for r in detail["reviews"])
    assert app_client.get("/api/products/nope").status_code == 404


def test_protected_routes_need_login(app_client):
    assert app_client.get("/api/me/cart").status_code == 401
    assert app_client.get("/api/orders").status_code == 401
    assert app_client.get("/api/packwise/orders").status_code == 401


def test_cart_stock_validation(app_client, customer):
    p = app_client.get("/api/products/orbit-smartwatch").json()
    r = app_client.put(f"/api/me/cart/{p['id']}", json={"quantity": p["stock"] + 1}, headers=customer)
    assert r.status_code == 409
    r = app_client.put(f"/api/me/cart/{p['id']}", json={"quantity": 2}, headers=customer)
    assert r.json()["count"] == 2 and r.json()["subtotal"] == p["price"] * 2
    r = app_client.put(f"/api/me/cart/{p['id']}", json={"quantity": 0}, headers=customer)
    assert r.json()["count"] == 0


def test_checkout_creates_persistent_order_and_decrements_stock(app_client, customer, place_order):
    before = app_client.get("/api/products/velvet-matte-lipstick").json()["stock"]
    order = place_order({"velvet-matte-lipstick": 2})
    assert order["code"].startswith("TOTE-")
    assert order["status"] == "awaiting_packing"
    assert [e["status"] for e in order["timeline"]] == ["placed", "awaiting_packing"]
    assert app_client.get("/api/products/velvet-matte-lipstick").json()["stock"] == before - 2
    assert app_client.get("/api/me/cart", headers=customer).json()["count"] == 0
    tracked = app_client.get(f"/api/orders/{order['code']}", headers=customer).json()
    assert tracked["id"] == order["id"]
    # another customer cannot see it
    other = app_client.post("/api/auth/register", json={"name": "Bo", "email": "bo@example.com", "password": "longpass1"})
    assert app_client.get(f"/api/orders/{order['code']}", headers=_auth(other.json()["token"])).status_code == 404


def test_checkout_rejects_empty_cart_and_unconfirmed_payment(app_client, customer):
    assert app_client.post("/api/orders/checkout", json=CHECKOUT, headers=customer).status_code == 400
    bad = {**CHECKOUT, "payment": {"method": "card", "confirm_simulated": False}}
    assert app_client.post("/api/orders/checkout", json=bad, headers=customer).status_code == 422


def test_wishlist_and_recent(app_client, customer):
    pid = app_client.get("/api/products/dot-grid-notebook").json()["id"]
    app_client.post(f"/api/me/wishlist/{pid}", headers=customer)
    app_client.post(f"/api/me/wishlist/{pid}", headers=customer)  # idempotent
    assert [p["id"] for p in app_client.get("/api/me/wishlist", headers=customer).json()] == [pid]
    app_client.post(f"/api/me/recent/{pid}", headers=customer)
    assert app_client.get("/api/me/recent", headers=customer).json()[0]["id"] == pid


def test_admin_product_management_is_protected(app_client, admin, customer, worker):
    body = {"name": "Test Tumbler", "category": "Home & Living", "price": 999, "stock": 5, "length_cm": 8,
            "width_cm": 8, "height_cm": 15, "weight_g": 300}
    assert app_client.post("/api/admin/products", json=body, headers=customer).status_code == 403
    assert app_client.post("/api/admin/products", json=body, headers=worker).status_code == 403
    r = app_client.post("/api/admin/products", json=body, headers=admin)
    assert r.status_code == 201
    pid = r.json()["id"]
    r = app_client.patch(f"/api/admin/products/{pid}", json={"is_active": False}, headers=admin)
    assert r.json()["is_active"] is False
    assert app_client.get(f"/api/products/{r.json()['slug']}").status_code == 404
    bad = app_client.patch(f"/api/admin/products/{pid}", json={"protection_material_code": "NOPE"}, headers=admin)
    assert bad.status_code == 422
