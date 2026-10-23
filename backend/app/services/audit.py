"""Audit trail helpers."""
from typing import Optional

from sqlalchemy.orm import Session

from ..models import AuditEvent, Order, OrderEvent


def log(db: Session, entity: str, action: str, actor: str, entity_id: Optional[int] = None,
        order_id: Optional[int] = None, **details):
    db.add(AuditEvent(entity=entity, entity_id=entity_id, order_id=order_id, action=action,
                      actor=actor, details=details))


def order_status(db: Session, order: Order, status: str, actor: str, note: str = ""):
    """Moves an order to a new status and appends to its customer-visible timeline."""
    if order.status == status:
        return
    previous = order.status
    order.status = status
    db.add(OrderEvent(order_id=order.id, status=status, note=note, actor=actor))
    log(db, "order", "status_change", actor, order.id, order.id, previous=previous, status=status, note=note)
