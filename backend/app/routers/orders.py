from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import serializers as S
from ..database import get_db
from ..models import Order
from ..schemas import CheckoutIn
from ..security import Principal, require_customer
from ..services import orders as order_service

router = APIRouter(prefix="/api/orders", tags=["Orders & tracking"])


@router.post("/checkout", status_code=201, summary="Place an order from the cart (payment is simulated)")
def checkout(body: CheckoutIn, p: Principal = Depends(require_customer), db: Session = Depends(get_db),
             idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=80)):
    order = order_service.checkout(db, p.user, body.contact.model_dump(), body.address.model_dump(),
                                   body.payment.model_dump(), idempotency_key=(idempotency_key or "").strip() or None)
    return S.order(order)


@router.get("", summary="The signed-in customer's orders")
def my_orders(p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    rows = db.query(Order).filter(Order.user_id == p.user.id).order_by(Order.id.desc()).all()
    return [S.order(o) for o in rows]


@router.get("/{code}", summary="Track one order (owner only)")
def track(code: str, p: Principal = Depends(require_customer), db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.code == code.upper()).first()
    if not o or (o.user_id != p.user.id and p.role != "admin"):
        raise HTTPException(404, "Order not found.")
    return S.order(o)
