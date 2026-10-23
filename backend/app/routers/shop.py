"""Customer cart, wishlist and recently viewed (all persisted server-side)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import serializers as S
from ..database import get_db
from ..models import CartItem, Product, RecentlyViewed, WishlistItem, utcnow
from ..schemas import CartMergeIn, CartQtyIn
from ..security import Principal, require_customer
from ..services.orders import shipping_for

router = APIRouter(prefix="/api/me", tags=["Cart, wishlist, recently viewed"])


def _cart(db: Session, user_id: int) -> dict:
    lines = db.query(CartItem).filter(CartItem.user_id == user_id).order_by(CartItem.id).all()
    items, subtotal, issues = [], 0.0, []
    for ln in lines:
        p = ln.product
        ok = p.is_active and ln.quantity <= p.stock
        if not ok:
            issues.append(f"{p.name}: only {p.stock if p.is_active else 0} available")
        line_total = round(p.price * ln.quantity, 2)
        subtotal += line_total
        items.append({"product": S.product(p), "quantity": ln.quantity, "line_total": line_total, "stock_ok": ok})
    subtotal = round(subtotal, 2)
    shipping = shipping_for(subtotal) if items else 0.0
    return {"items": items, "subtotal": subtotal, "shipping": shipping, "total": round(subtotal + shipping, 2),
            "count": sum(i["quantity"] for i in items), "issues": issues}


def _product(db: Session, pid: int) -> Product:
    p = db.get(Product, pid)
    if not p or not p.is_active:
        raise HTTPException(404, "Product not found.")
    return p


@router.get("/cart", summary="Current cart with totals and stock checks")
def get_cart(p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    return _cart(db, p.user.id)


@router.put("/cart/{product_id}", summary="Set quantity for a product (0 removes it)")
def set_qty(product_id: int, body: CartQtyIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    prod = _product(db, product_id)
    line = db.query(CartItem).filter(CartItem.user_id == p.user.id, CartItem.product_id == product_id).first()
    if body.quantity == 0:
        if line:
            db.delete(line)
    else:
        if body.quantity > prod.stock:
            raise HTTPException(409, f"Only {prod.stock} of {prod.name} in stock.")
        if line:
            line.quantity = body.quantity
        else:
            db.add(CartItem(user_id=p.user.id, product_id=product_id, quantity=body.quantity))
    db.commit()
    return _cart(db, p.user.id)


@router.delete("/cart", summary="Empty the cart")
def clear_cart(p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    db.query(CartItem).filter(CartItem.user_id == p.user.id).delete()
    db.commit()
    return _cart(db, p.user.id)


@router.post("/cart/merge", summary="Merge a guest cart into the account after sign-in")
def merge_cart(body: CartMergeIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    for raw in body.items:
        try:
            pid, qty = int(raw.get("product_id")), int(raw.get("quantity"))
        except (TypeError, ValueError):
            continue
        prod = db.get(Product, pid)
        if not prod or not prod.is_active or qty <= 0:
            continue
        line = db.query(CartItem).filter(CartItem.user_id == p.user.id, CartItem.product_id == pid).first()
        new_qty = min((line.quantity if line else 0) + qty, prod.stock, 99)
        if new_qty <= 0:
            continue
        if line:
            line.quantity = new_qty
        else:
            db.add(CartItem(user_id=p.user.id, product_id=pid, quantity=new_qty))
    db.commit()
    return _cart(db, p.user.id)


@router.get("/wishlist", summary="Saved products")
def wishlist(p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    rows = db.query(WishlistItem).filter(WishlistItem.user_id == p.user.id).order_by(WishlistItem.id.desc()).all()
    return [S.product(r.product) for r in rows if r.product.is_active]


@router.post("/wishlist/{product_id}", status_code=201, summary="Save a product")
def add_wish(product_id: int, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    _product(db, product_id)
    if not db.query(WishlistItem).filter(WishlistItem.user_id == p.user.id, WishlistItem.product_id == product_id).first():
        db.add(WishlistItem(user_id=p.user.id, product_id=product_id))
        db.commit()
    return {"ok": True}


@router.delete("/wishlist/{product_id}", summary="Remove a saved product")
def remove_wish(product_id: int, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    db.query(WishlistItem).filter(WishlistItem.user_id == p.user.id, WishlistItem.product_id == product_id).delete()
    db.commit()
    return {"ok": True}


@router.get("/recent", summary="Recently viewed products")
def recent(p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    rows = (db.query(RecentlyViewed).filter(RecentlyViewed.user_id == p.user.id)
            .order_by(RecentlyViewed.viewed_at.desc()).limit(8).all())
    return [S.product(r.product) for r in rows if r.product.is_active]


@router.post("/recent/{product_id}", summary="Record a product view")
def add_recent(product_id: int, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    _product(db, product_id)
    row = db.query(RecentlyViewed).filter(RecentlyViewed.user_id == p.user.id,
                                          RecentlyViewed.product_id == product_id).first()
    if row:
        row.viewed_at = utcnow()
    else:
        db.add(RecentlyViewed(user_id=p.user.id, product_id=product_id))
    db.commit()
    return {"ok": True}
