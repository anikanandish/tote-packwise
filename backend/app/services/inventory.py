"""Inventory operations. Every change goes through a guarded UPDATE so two workers
can never reserve the same unit, and every change writes a StockMovement row.

All functions here run inside the caller's transaction; the caller commits or
rolls back, so a failure part-way through leaves inventory untouched.
"""
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import Carton, Material, Reservation, StockMovement

MODELS = {"carton": Carton, "material": Material}


class StockError(Exception):
    pass


def _record(db: Session, item_type: str, item_id: int, kind: str, stock_delta: int, reserved_delta: int,
            reason: str, actor: str, plan_id: Optional[int] = None, order_id: Optional[int] = None):
    model = MODELS[item_type]
    row = db.get(model, item_id)
    db.refresh(row)
    db.add(StockMovement(item_type=item_type, item_id=item_id, item_code=row.code, kind=kind,
                         stock_delta=stock_delta, reserved_delta=reserved_delta,
                         stock_after=row.stock, reserved_after=row.reserved, reason=reason,
                         plan_id=plan_id, order_id=order_id, actor=actor))


def reserve(db: Session, item_type: str, item_id: int, qty: int, plan_id: int, order_id: int, actor: str) -> Reservation:
    if qty <= 0:
        raise StockError("Reservation quantity must be positive.")
    model = MODELS[item_type]
    res = db.execute(update(model)
                     .where(model.id == item_id, model.is_active.is_(True), model.stock - model.reserved >= qty)
                     .values(reserved=model.reserved + qty))
    row = db.get(model, item_id)
    if res.rowcount != 1:
        db.refresh(row)
        raise StockError(f"Not enough {row.name} available: need {qty}, "
                         f"{max(row.stock - row.reserved, 0)} free.")
    r = Reservation(plan_id=plan_id, item_type=item_type, item_id=item_id, item_code=row.code,
                    quantity=qty, status="active")
    db.add(r)
    _record(db, item_type, item_id, "reserve", 0, qty, f"Reserved for packing plan #{plan_id}", actor, plan_id, order_id)
    return r


def release_plan(db: Session, plan_id: int, order_id: int, actor: str, reason: str) -> int:
    """Releases every active reservation of a plan. Returns how many were released."""
    released = 0
    for r in db.query(Reservation).filter(Reservation.plan_id == plan_id, Reservation.status == "active").all():
        model = MODELS[r.item_type]
        res = db.execute(update(Reservation).where(Reservation.id == r.id, Reservation.status == "active")
                         .values(status="released"))
        if res.rowcount != 1:
            continue
        db.execute(update(model).where(model.id == r.item_id).values(reserved=model.reserved - r.quantity))
        _record(db, r.item_type, r.item_id, "release", 0, -r.quantity, reason, actor, plan_id, order_id)
        released += 1
    return released


def consume_reservation(db: Session, r: Reservation, actual_qty: int, actor: str, plan_id: int, order_id: int):
    """Turns a reservation into real consumption. actual_qty may differ for materials."""
    model = MODELS[r.item_type]
    extra = actual_qty - r.quantity
    if extra > 0:
        res = db.execute(update(model).where(model.id == r.item_id, model.stock - model.reserved >= extra)
                         .values(stock=model.stock - actual_qty, reserved=model.reserved - r.quantity))
        if res.rowcount != 1:
            row = db.get(model, r.item_id)
            raise StockError(f"Cannot use {actual_qty} {row.name}: only {r.quantity} reserved and "
                             f"{max(row.stock - row.reserved, 0)} extra free.")
    else:
        db.execute(update(model).where(model.id == r.item_id)
                   .values(stock=model.stock - actual_qty, reserved=model.reserved - r.quantity))
    db.execute(update(Reservation).where(Reservation.id == r.id).values(status="consumed"))
    _record(db, r.item_type, r.item_id, "consume", -actual_qty, -r.quantity,
            f"Used for packing plan #{plan_id} (reserved {r.quantity}, used {actual_qty})", actor, plan_id, order_id)


def consume_unreserved(db: Session, material: Material, qty: int, actor: str, plan_id: int, order_id: int):
    res = db.execute(update(Material).where(Material.id == material.id, Material.stock - Material.reserved >= qty)
                     .values(stock=Material.stock - qty))
    if res.rowcount != 1:
        raise StockError(f"Not enough {material.name} free to record {qty} {material.unit} used.")
    _record(db, "material", material.id, "consume", -qty, 0,
            f"Extra material used for packing plan #{plan_id} (not reserved)", actor, plan_id, order_id)


def adjust(db: Session, item_type: str, item_id: int, delta: int, reason: str, actor: str):
    model = MODELS[item_type]
    if delta == 0:
        raise StockError("Adjustment must not be zero.")
    res = db.execute(update(model).where(model.id == item_id, model.stock + delta >= model.reserved)
                     .values(stock=model.stock + delta))
    if res.rowcount != 1:
        raise StockError("Stock cannot drop below the quantity currently reserved.")
    _record(db, item_type, item_id, "adjust", delta, 0, reason, actor)


def initial(db: Session, item_type: str, row, actor: str, reason: str = "Initial stock"):
    db.flush()
    _record(db, item_type, row.id, "initial", row.stock, 0, reason, actor)
