"""Warehouse endpoints for workers (and admins)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import serializers as S
from ..database import get_db
from ..models import AuditEvent, Carton, Material, Order, PackingCompletion, PackingPlan
from ..schemas import CompleteIn, DispatchIn, OverrideIn, ReasonIn
from ..security import Principal, require_staff
from ..services import packing
from ..services.reports import low_stock

router = APIRouter(prefix="/api/packwise", tags=["PackWise — warehouse"])

QUEUE_GROUPS = {
    "pending": ("placed", "awaiting_packing"),
    "in_progress": ("packing_in_progress",),
    "completed": ("packed", "ready_for_dispatch", "dispatched"),
}


def _order(db: Session, order_id: int) -> Order:
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found.")
    return o


def _latest_plan(db: Session, order_id: int) -> Optional[PackingPlan]:
    return (db.query(PackingPlan).filter(PackingPlan.order_id == order_id)
            .order_by(PackingPlan.id.desc()).first())


@router.get("/summary", summary="Queue counts for the worker dashboard")
def summary(p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    orders = db.query(Order).all()
    open_orders = [o for o in orders if o.status in QUEUE_GROUPS["pending"]]
    planned = {pl.order_id for pl in db.query(PackingPlan).filter(PackingPlan.status == "recommended")}
    return {
        "pending": len(open_orders),
        "awaiting_recommendation": sum(1 for o in open_orders if o.id not in planned),
        "recommended": sum(1 for o in open_orders if o.id in planned),
        "in_progress": sum(1 for o in orders if o.status in QUEUE_GROUPS["in_progress"]),
        "completed": sum(1 for o in orders if o.status in QUEUE_GROUPS["completed"]),
        "fragile_open": sum(1 for o in orders if o.status not in QUEUE_GROUPS["completed"]
                            and any(i.product.fragile for i in o.items)),
        "priority_open": sum(1 for o in orders if o.priority and o.status not in QUEUE_GROUPS["completed"]),
        "low_stock": low_stock(db),
        "worker": p.worker_name or (p.user.name if p.user else None),
        "role": p.role,
    }


@router.get("/orders", summary="Order queue. group = pending | in_progress | completed | all")
def queue(group: str = "pending", p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    q = db.query(Order)
    if group in QUEUE_GROUPS:
        q = q.filter(Order.status.in_(QUEUE_GROUPS[group]))
    rows = q.order_by(Order.priority.desc(), Order.created_at.asc()).limit(200).all()
    out = []
    for o in rows:
        d = S.order(o, staff=True)
        d.pop("contact"); d.pop("address"); d.pop("timeline")
        latest = _latest_plan(db, o.id)
        d["plan"] = S.plan(latest, full=False) if latest else None
        out.append(d)
    # fragile first among equal priority, keeping FIFO otherwise
    out.sort(key=lambda d: (not d["priority"], not d["fragile"], d["created_at"]))
    return out


@router.get("/orders/{order_id}", summary="Order detail with items, packaging metadata and plans")
def order_detail(order_id: int, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    o = _order(db, order_id)
    d = S.order(o, staff=True)
    d.pop("contact")
    d["address"] = {"city": o.address.get("city"), "state": o.address.get("state"),
                    "postal_code": o.address.get("postal_code")}
    plans = db.query(PackingPlan).filter(PackingPlan.order_id == o.id).order_by(PackingPlan.id.desc()).all()
    d["plans"] = [S.plan(pl, full=False) for pl in plans]
    current = next((pl for pl in plans if pl.status in ("recommended", "accepted", "completed", "no_fit")), None)
    d["current_plan"] = S.plan(current) if current else None
    comp = db.query(PackingCompletion).filter(PackingCompletion.order_id == o.id).first()
    d["completion"] = ({"materials_used": comp.materials_used, "actual_cost": comp.actual_cost,
                        "actual_savings": comp.actual_savings, "baseline_cost": comp.baseline_cost,
                        "actor": comp.actor, "created_at": comp.created_at.isoformat(), "notes": comp.notes}
                       if comp else None)
    d["checklist_items"] = packing.CHECKLIST
    return d


@router.post("/orders/{order_id}/recommend", summary="Ask the C++ engine for a carton recommendation")
def recommend(order_id: int, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    plan = packing.recommend(db, _order(db, order_id), p.actor)
    return S.plan(plan)


@router.get("/plans/{plan_id}", summary="Full packing plan with placements and snapshots")
def get_plan(plan_id: int, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    plan = db.get(PackingPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Packing plan not found.")
    return S.plan(plan)


@router.post("/plans/{plan_id}/accept", summary="Accept a plan and reserve carton + materials")
def accept(plan_id: int, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    return S.plan(packing.accept(db, plan_id, p.actor))


@router.post("/plans/{plan_id}/cancel", summary="Cancel a plan and release its reservations")
def cancel(plan_id: int, body: ReasonIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    return S.plan(packing.cancel(db, plan_id, p.actor, body.reason))


@router.post("/plans/{plan_id}/override", summary="Choose another carton (reason required, safety rules enforced)")
def override(plan_id: int, body: OverrideIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    return S.plan(packing.override(db, plan_id, body.carton_id, body.reason.strip(), p.actor))


@router.post("/plans/{plan_id}/complete", summary="Complete packing; consumes reserved stock exactly once")
def complete(plan_id: int, body: CompleteIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    comp, already = packing.complete(db, plan_id, [m.model_dump() for m in body.materials_used], body.checklist,
                                     body.notes, p.actor)
    return {"already_completed": already, "plan_id": comp.plan_id, "order_id": comp.order_id,
            "carton": comp.carton_code, "materials_used": comp.materials_used, "actual_cost": comp.actual_cost,
            "baseline_cost": comp.baseline_cost, "actual_savings": comp.actual_savings,
            "completed_at": comp.created_at.isoformat()}


@router.post("/orders/{order_id}/dispatch", summary="Mark packed order ready for dispatch / dispatched")
def dispatch(order_id: int, body: DispatchIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    o = packing.advance_dispatch(db, _order(db, order_id), body.status, p.actor)
    return {"id": o.id, "status": o.status}


@router.get("/cartons", summary="Carton catalogue as seen by workers")
def cartons(p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    return [S.carton(c) for c in db.query(Carton).order_by(Carton.length_mm * Carton.width_mm * Carton.height_mm)]


@router.get("/materials", summary="Protective materials as seen by workers")
def materials(p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    return [S.material(m) for m in db.query(Material).order_by(Material.name)]


@router.get("/orders/{order_id}/history", summary="Audit trail for one order")
def order_history(order_id: int, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    _order(db, order_id)
    rows = db.query(AuditEvent).filter(AuditEvent.order_id == order_id).order_by(AuditEvent.id).all()
    return [{"id": e.id, "entity": e.entity, "action": e.action, "actor": e.actor, "details": e.details,
             "created_at": e.created_at.isoformat()} for e in rows]
