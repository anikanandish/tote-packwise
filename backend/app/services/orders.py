"""Checkout: turns the customer's server-side cart into a persistent order in one transaction."""
import secrets
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import CartItem, Order, OrderEvent, OrderItem, Product, User
from . import audit


def new_order_code(db: Session) -> str:
    while True:
        code = "TOTE-" + secrets.token_hex(3).upper()
        if not db.query(Order).filter(Order.code == code).first():
            return code


def shipping_for(subtotal: float) -> float:
    return 0.0 if subtotal >= settings.free_shipping_over else settings.shipping_flat


def checkout(db: Session, user: User, contact: dict, address: dict, payment: dict,
             idempotency_key: Optional[str] = None) -> Order:
    """Places one order. Safe to call twice for the same checkout:
    * with the same Idempotency-Key the first order is returned again (no second order, no
      second stock deduction);
    * without a key, the cart is emptied in the same transaction and a second, overlapping
      submit finds the cart already taken and is rolled back."""
    if idempotency_key:
        existing = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
        if existing:
            if existing.user_id != user.id:
                raise HTTPException(409, "This checkout key belongs to another account.")
            return existing
    lines = db.query(CartItem).filter(CartItem.user_id == user.id).all()
    if not lines:
        raise HTTPException(400, "Your bag is empty.")

    try:
        subtotal = 0.0
        order = Order(code=new_order_code(db), user_id=user.id, status="placed", contact=contact, address=address,
                      subtotal=0, shipping=0, total=0, payment_ref="SIM-" + secrets.token_hex(4).upper(),
                      idempotency_key=idempotency_key)
        db.add(order)
        db.flush()
        for line in lines:
            p: Product = line.product
            if not p.is_active:
                raise ValueError(f"{p.name} is no longer available.")
            # Guarded decrement: never sells stock that is not there, even with simultaneous checkouts.
            res = db.execute(update(Product).where(Product.id == p.id, Product.stock >= line.quantity)
                             .values(stock=Product.stock - line.quantity))
            if res.rowcount != 1:
                db.refresh(p)
                raise ValueError(f"Only {p.stock} of {p.name} left in stock.")
            db.add(OrderItem(order_id=order.id, product_id=p.id, name=p.name, unit_price=p.price,
                             quantity=line.quantity))
            subtotal += p.price * line.quantity
        order.subtotal = round(subtotal, 2)
        order.shipping = shipping_for(subtotal)
        order.total = round(order.subtotal + order.shipping, 2)
        db.add(OrderEvent(order_id=order.id, status="placed", note="Order placed (simulated payment)",
                          actor=f"customer:{user.email}"))
        actor = f"customer:{user.email}"
        audit.log(db, "order", "created", actor, order.id, order.id, total=order.total,
                  payment="simulated", method=payment.get("method", "card"))
        audit.order_status(db, order, "awaiting_packing", "system", "Sent to the PackWise warehouse queue")
        removed = db.query(CartItem).filter(CartItem.id.in_([ln.id for ln in lines])).delete(synchronize_session=False)
        if removed != len(lines):
            raise ValueError("This bag was already checked out. Check your orders before trying again.")
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(409, str(e))
    except IntegrityError:
        db.rollback()   # the same Idempotency-Key committed by a parallel request
        existing = db.query(Order).filter(Order.idempotency_key == idempotency_key).first() if idempotency_key else None
        if existing and existing.user_id == user.id:
            return existing
        raise HTTPException(409, "This order was already placed.")
    db.refresh(order)
    return order
