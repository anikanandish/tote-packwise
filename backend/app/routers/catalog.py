from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import serializers as S
from ..database import get_db
from ..models import Product, Review

router = APIRouter(prefix="/api/products", tags=["Catalogue"])


@router.get("", summary="List, search, filter and sort products")
def list_products(q: Optional[str] = Query(None, max_length=100), category: Optional[str] = None,
                  min_price: Optional[float] = Query(None, ge=0), max_price: Optional[float] = Query(None, ge=0),
                  sort: Literal["featured", "price_asc", "price_desc", "rating", "newest"] = "featured",
                  featured: Optional[bool] = None, in_stock: Optional[bool] = None,
                  limit: int = Query(60, ge=1, le=100), db: Session = Depends(get_db)):
    qry = db.query(Product).filter(Product.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        qry = qry.filter(or_(Product.name.ilike(like), Product.brand.ilike(like), Product.category.ilike(like)))
    if category:
        qry = qry.filter(Product.category == category)
    if min_price is not None:
        qry = qry.filter(Product.price >= min_price)
    if max_price is not None:
        qry = qry.filter(Product.price <= max_price)
    if featured is not None:
        qry = qry.filter(Product.featured.is_(featured))
    if in_stock:
        qry = qry.filter(Product.stock > 0)
    order = {"price_asc": Product.price.asc(), "price_desc": Product.price.desc(), "rating": Product.rating.desc(),
             "newest": Product.created_at.desc(), "featured": Product.featured.desc()}[sort]
    items = qry.order_by(order, Product.id).limit(limit).all()
    return {"items": [S.product(p) for p in items], "count": len(items)}


@router.get("/categories", summary="Categories with product counts")
def categories(db: Session = Depends(get_db)):
    rows = (db.query(Product.category, func.count(Product.id)).filter(Product.is_active.is_(True))
            .group_by(Product.category).order_by(Product.category).all())
    return [{"name": c, "count": n} for c, n in rows]


@router.get("/{slug}", summary="Product details with demo reviews")
def product_detail(slug: str, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.slug == slug, Product.is_active.is_(True)).first()
    if not p:
        raise HTTPException(404, "Product not found.")
    d = S.product(p, packaging=True)
    d["reviews"] = [{"author": r.author, "rating": r.rating, "title": r.title, "body": r.body, "is_demo": r.is_demo,
                     "created_at": r.created_at.isoformat()}
                    for r in db.query(Review).filter(Review.product_id == p.id).order_by(Review.id.desc())]
    related = (db.query(Product).filter(Product.category == p.category, Product.id != p.id,
                                        Product.is_active.is_(True)).limit(4).all())
    d["related"] = [S.product(r) for r in related]
    return d
