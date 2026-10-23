"""Packing-plan lifecycle: recommend -> accept (reserve) -> complete (consume),
plus cancel and worker override. Each public function is one database transaction."""
import copy
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import (Carton, Material, Order, PackingCompletion, PackingPlan, PlacementRecord, Reservation,
                      WorkerOverride, utcnow)
from . import audit, feasibility, inventory
from .packer_client import PackerError, PackerUnavailable

ACTIVE_PLAN = ("recommended", "accepted")
CHECKLIST = {
    "items_match_order": "Every item and quantity matches the order",
    "fragile_protection_applied": "Fragile items wrapped with the required material",
    "placement_followed": "Items placed in the engine's sequence and positions",
    "void_fill_added": "Empty space filled so nothing moves",
    "carton_sealed": "Carton sealed and labelled",
}


def _conflict(msg: str):
    raise HTTPException(409, msg)


def _get_plan(db: Session, plan_id: int) -> PackingPlan:
    plan = db.get(PackingPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Packing plan not found.")
    return plan


def _evaluate_or_fail(db: Session, order: Order, actor: str, only_carton_id: Optional[int] = None) -> dict:
    try:
        return feasibility.evaluate(db, order, only_carton_id)
    except PackerUnavailable as e:
        db.rollback()
        audit.log(db, "plan", "recommendation_failed", actor, order_id=order.id, error=str(e), kind="unavailable")
        db.commit()
        raise HTTPException(503, f"The packing engine is offline. {e} Start the C++ service and try again.")
    except PackerError as e:
        db.rollback()
        audit.log(db, "plan", "recommendation_failed", actor, order_id=order.id, error=e.message, kind=e.code)
        db.commit()
        raise HTTPException(502, f"The packing engine rejected the request: {e.message}")


def _create_plan(db: Session, order: Order, evaluation: dict, selected: Optional[dict], actor: str,
                 is_override: bool = False, parent: Optional[PackingPlan] = None) -> PackingPlan:
    base = evaluation["baseline"]
    snapshot = {"evaluation": evaluation, "selected": copy.deepcopy(selected)}
    plan = PackingPlan(order_id=order.id, created_by=actor, snapshot=snapshot, is_override=is_override,
                       parent_plan_id=parent.id if parent else None)
    if selected is None:
        plan.status = "no_fit"
        db.add(plan)
        db.flush()
        return plan

    plan.status = "recommended"
    plan.carton_id = selected["carton"]["id"]
    plan.recommended_carton_id = parent.recommended_carton_id if parent else selected["carton"]["id"]
    plan.estimated_cost = selected["cost"]["total"]
    plan.utilization = selected.get("utilization")
    plan.void_cm3 = selected.get("void_cm3")
    plan.carton_volume_cm3 = selected["carton"]["volume_cm3"]
    if base.get("available"):
        plan.baseline_cost = base["cost"]["total"]
        plan.baseline_volume_cm3 = base["volume_cm3"]
        if plan.estimated_cost is not None:
            plan.estimated_savings = round(plan.baseline_cost - plan.estimated_cost, 2)
    db.add(plan)
    db.flush()

    units = {u["ref"]: u for u in evaluation["units"]}
    for p in selected["placement"]["placements"]:
        u = units[p["id"]]
        db.add(PlacementRecord(plan_id=plan.id, seq=p["seq"], unit_ref=p["id"], product_id=u["product_id"],
                               product_name=u["name"], x_cm=p["x"] / 10, y_cm=p["y"] / 10, z_cm=p["z"] / 10,
                               dx_cm=p["dx"] / 10, dy_cm=p["dy"] / 10, dz_cm=p["dz"] / 10,
                               padding_cm=u["padding_cm"], rotated=p["rotated"]))
    return plan


def _supersede_open_recommendations(db: Session, order_id: int, actor: str):
    for old in db.query(PackingPlan).filter(PackingPlan.order_id == order_id,
                                            PackingPlan.status == "recommended").all():
        old.status = "superseded"
        audit.log(db, "plan", "superseded", actor, old.id, order_id)


# ----------------------------------------------------------------- recommend
def recommend(db: Session, order: Order, actor: str) -> PackingPlan:
    if order.status not in ("placed", "awaiting_packing"):
        if db.query(PackingPlan).filter(PackingPlan.order_id == order.id, PackingPlan.status == "accepted").count():
            _conflict("This order already has an accepted plan. Cancel it before requesting a new recommendation.")
        _conflict(f"Order is '{order.status}' and cannot be re-planned.")

    evaluation = _evaluate_or_fail(db, order, actor)
    chosen_id = evaluation["chosen_carton_id"]
    selected = next((ev for ev in evaluation["evaluations"] if ev["carton"]["id"] == chosen_id), None)

    previous = db.query(PackingPlan).filter(PackingPlan.order_id == order.id).count()
    _supersede_open_recommendations(db, order.id, actor)
    plan = _create_plan(db, order, evaluation, selected, actor)
    audit.log(db, "plan", "no_fit" if plan.status == "no_fit" else "recommended", actor, plan.id, order.id,
              carton=selected["carton"]["code"] if selected else None, estimated_cost=plan.estimated_cost,
              baseline_cost=plan.baseline_cost, retry=previous > 0,
              reasons=None if selected else [r for ev in evaluation["evaluations"] for r in ev["reasons"]][:20])
    if order.status == "placed":
        audit.order_status(db, order, "awaiting_packing", actor)
    db.commit()
    return plan


# ----------------------------------------------------------------- accept
def accept(db: Session, plan_id: int, actor: str) -> PackingPlan:
    plan = _get_plan(db, plan_id)
    if plan.status == "accepted":
        _conflict("This plan is already accepted and its stock is reserved.")
    if plan.status != "recommended":
        _conflict(f"Only recommended plans can be accepted (this plan is '{plan.status}').")
    order = plan.order
    if db.query(PackingPlan).filter(PackingPlan.order_id == order.id, PackingPlan.status == "accepted",
                                    PackingPlan.id != plan.id).count():
        _conflict("Another plan for this order is already accepted.")

    selected = plan.snapshot["selected"]
    carton = db.get(Carton, plan.carton_id)
    if not carton or not carton.is_active:
        _conflict("The selected carton is no longer active. Request a new recommendation.")
    snap_dims = selected["carton"]["dims_cm"]
    if [carton.length_cm, carton.width_cm, carton.height_cm] != snap_dims or carton.max_weight_g != selected["carton"]["max_weight_g"]:
        _conflict("The carton's dimensions or weight limit changed since this plan was calculated. "
                  "Request a new recommendation.")

    try:
        res = db.execute(update(PackingPlan).where(PackingPlan.id == plan.id, PackingPlan.status == "recommended")
                         .values(status="accepted", accepted_at=utcnow(), accepted_by=actor))
        if res.rowcount != 1:
            raise inventory.StockError("This plan was changed by someone else. Refresh and try again.")
        inventory.reserve(db, "carton", carton.id, 1, plan.id, order.id, actor)
        for ln in selected["materials"]:
            mat = db.query(Material).filter(Material.code == ln["code"]).first()
            if not mat:
                raise inventory.StockError(f"Material {ln['code']} no longer exists.")
            if ln["quantity"] > 0:
                inventory.reserve(db, "material", mat.id, ln["quantity"], plan.id, order.id, actor)
        audit.order_status(db, order, "packing_in_progress", actor, f"Packing started in {carton.name} carton")
        audit.log(db, "plan", "accepted", actor, plan.id, order.id, carton=carton.code,
                  reserved=[{"code": carton.code, "qty": 1}] + [{"code": m["code"], "qty": m["quantity"]}
                                                                for m in selected["materials"]])
        db.commit()
    except inventory.StockError as e:
        db.rollback()
        audit.log(db, "plan", "accept_failed", actor, plan.id, order.id, error=str(e))
        db.commit()
        _conflict(f"{e} Stock changed since the recommendation was made; request a new recommendation.")
    db.refresh(plan)
    return plan


# ----------------------------------------------------------------- cancel
def cancel(db: Session, plan_id: int, actor: str, reason: str) -> PackingPlan:
    plan = _get_plan(db, plan_id)
    if plan.status not in ACTIVE_PLAN:
        _conflict(f"A '{plan.status}' plan cannot be cancelled.")
    was_accepted = plan.status == "accepted"
    res = db.execute(update(PackingPlan).where(PackingPlan.id == plan.id, PackingPlan.status.in_(ACTIVE_PLAN))
                     .values(status="cancelled", cancelled_at=utcnow(), cancel_reason=reason))
    if res.rowcount != 1:
        db.rollback()
        _conflict("The plan changed while cancelling. Refresh and try again.")
    released = inventory.release_plan(db, plan.id, plan.order_id, actor, f"Plan #{plan.id} cancelled: {reason}")
    if was_accepted:
        audit.order_status(db, plan.order, "awaiting_packing", actor, "Packing plan cancelled")
    audit.log(db, "plan", "cancelled", actor, plan.id, plan.order_id, reason=reason, released=released)
    db.commit()
    db.refresh(plan)
    return plan


# ----------------------------------------------------------------- override
def override(db: Session, plan_id: int, carton_id: int, reason: str, actor: str) -> PackingPlan:
    plan = _get_plan(db, plan_id)
    if plan.status not in ACTIVE_PLAN:
        _conflict(f"A '{plan.status}' plan cannot be overridden.")
    if plan.carton_id == carton_id:
        raise HTTPException(422, "That carton is already selected.")
    target = db.get(Carton, carton_id)
    if not target:
        raise HTTPException(404, "Carton not found.")
    order = plan.order

    evaluation = _evaluate_or_fail(db, order, actor, only_carton_id=carton_id)
    ev = next((e for e in evaluation["evaluations"] if e["carton"]["id"] == carton_id), None)
    if not ev or ev["status"] != "feasible":
        audit.log(db, "plan", "override_rejected", actor, plan.id, order.id, carton=target.code, reason=reason,
                  rejections=ev["reasons"] if ev else ["not evaluated"])
        db.commit()
        raise HTTPException(422, {"message": f"{target.name} cannot be used for this order.",
                                  "reasons": ev["reasons"] if ev else []})

    was_accepted = plan.status == "accepted"
    original_cost, original_util = plan.estimated_cost, plan.utilization
    original_code = plan.carton.code if plan.carton else "?"
    res = db.execute(update(PackingPlan).where(PackingPlan.id == plan.id, PackingPlan.status.in_(ACTIVE_PLAN))
                     .values(status="superseded"))
    if res.rowcount != 1:
        db.rollback()
        _conflict("The plan changed while overriding. Refresh and try again.")
    if was_accepted:
        inventory.release_plan(db, plan.id, order.id, actor, f"Plan #{plan.id} replaced by worker override")
        audit.order_status(db, order, "awaiting_packing", actor, "Carton changed by worker override")

    ev = copy.deepcopy(ev)
    ev["why"] = [f"Worker override: {reason}"]
    new_plan = _create_plan(db, order, evaluation, ev, actor, is_override=True, parent=plan)
    new_plan.snapshot = {**new_plan.snapshot, "override": {
        "original_plan_id": plan.id, "original_carton": original_code, "reason": reason, "actor": actor,
        "original_cost": original_cost, "original_utilization": original_util}}
    db.add(WorkerOverride(order_id=order.id, original_plan_id=plan.id, new_plan_id=new_plan.id,
                          original_carton_code=original_code, selected_carton_code=target.code, reason=reason,
                          actor=actor, original_cost=original_cost, new_cost=new_plan.estimated_cost,
                          original_utilization=original_util, new_utilization=new_plan.utilization))
    audit.log(db, "plan", "override", actor, new_plan.id, order.id, original_plan=plan.id,
              original_carton=original_code, selected_carton=target.code, reason=reason,
              original_cost=original_cost, new_cost=new_plan.estimated_cost)
    db.commit()
    return new_plan


# ----------------------------------------------------------------- complete
def complete(db: Session, plan_id: int, materials_used: Optional[list[dict]], checklist: dict, notes: str,
             actor: str) -> tuple[PackingCompletion, bool]:
    """Returns (completion, already_completed). Safe to call repeatedly."""
    plan = _get_plan(db, plan_id)
    existing = db.query(PackingCompletion).filter(PackingCompletion.plan_id == plan.id).first()
    if plan.status == "completed" and existing:
        return existing, True
    if plan.status != "accepted":
        _conflict(f"Only an accepted plan can be completed (this plan is '{plan.status}').")

    selected = plan.snapshot["selected"]
    units = plan.snapshot["evaluation"]["units"]
    has_fragile = any(u["fragile"] for u in units)
    required = [k for k in CHECKLIST if k != "fragile_protection_applied" or has_fragile]
    missing = [CHECKLIST[k] for k in required if not checklist.get(k)]
    if missing:
        raise HTTPException(422, {"message": "Finish the packing checklist first.", "missing": missing})

    reservations = db.query(Reservation).filter(Reservation.plan_id == plan.id, Reservation.status == "active").all()
    reserved_mat = {r.item_code: r for r in reservations if r.item_type == "material"}
    used = {m["code"]: int(m["quantity"]) for m in (materials_used or [])}
    for code, r in reserved_mat.items():
        used.setdefault(code, r.quantity)
    if any(q < 0 for q in used.values()):
        raise HTTPException(422, "Material quantities cannot be negative.")

    protection = feasibility.protection_requirements(units)
    short = [f"{code}: need at least {q}, recorded {used.get(code, 0)}" for code, q in protection.items()
             if used.get(code, 0) < q]
    if short:
        raise HTTPException(422, {"message": "Required protective material was not recorded as used. "
                                             "Fragile and special-handling items cannot ship without it.",
                                  "missing": short})

    snap_costs = {ln["code"]: ln["unit_cost"] for ln in selected["materials"]}
    try:
        res = db.execute(update(PackingPlan).where(PackingPlan.id == plan.id, PackingPlan.status == "accepted")
                         .values(status="completed", completed_at=utcnow()))
        if res.rowcount != 1:
            db.rollback()
            db.refresh(plan)
            existing = db.query(PackingCompletion).filter(PackingCompletion.plan_id == plan.id).first()
            if existing:
                return existing, True
            _conflict("The plan changed while completing. Refresh and try again.")

        for r in reservations:
            if r.item_type == "carton":
                inventory.consume_reservation(db, r, 1, actor, plan.id, plan.order_id)
        used_lines = []
        for code, qty in used.items():
            mat = db.query(Material).filter(Material.code == code).first()
            if not mat:
                raise inventory.StockError(f"Unknown material {code}.")
            if code in reserved_mat:
                inventory.consume_reservation(db, reserved_mat[code], qty, actor, plan.id, plan.order_id)
            elif qty > 0:
                inventory.consume_unreserved(db, mat, qty, actor, plan.id, plan.order_id)
            unit_cost = snap_costs.get(code, mat.unit_cost)
            used_lines.append({"code": code, "name": mat.name, "unit": mat.unit, "quantity": qty,
                               "unit_cost": unit_cost})

        carton_cost = selected["carton"]["unit_cost"]
        costs_known = carton_cost is not None and all(ln["unit_cost"] is not None for ln in used_lines if ln["quantity"])
        actual = round(carton_cost + sum(ln["quantity"] * (ln["unit_cost"] or 0) for ln in used_lines), 2) \
            if costs_known else None
        savings = round(plan.baseline_cost - actual, 2) if (actual is not None and plan.baseline_cost is not None) else None

        completion = PackingCompletion(plan_id=plan.id, order_id=plan.order_id, carton_id=plan.carton_id,
                                       carton_code=selected["carton"]["code"], materials_used=used_lines,
                                       actual_cost=actual, baseline_cost=plan.baseline_cost,
                                       actual_savings=savings, checklist=checklist, notes=notes or "", actor=actor)
        db.add(completion)
        audit.order_status(db, plan.order, "packed", actor, f"Packed in {selected['carton']['name']} carton")
        audit.log(db, "plan", "completed", actor, plan.id, plan.order_id, carton=selected["carton"]["code"],
                  materials=used_lines, actual_cost=actual, baseline_cost=plan.baseline_cost, savings=savings)
        db.commit()
        return completion, False
    except inventory.StockError as e:
        db.rollback()
        raise HTTPException(409, str(e))


DISPATCH_FLOW = {"packed": "ready_for_dispatch", "ready_for_dispatch": "dispatched"}


def advance_dispatch(db: Session, order: Order, status: str, actor: str) -> Order:
    if DISPATCH_FLOW.get(order.status) != status:
        _conflict(f"Cannot move an order from '{order.status}' to '{status}'.")
    audit.order_status(db, order, status, actor)
    db.commit()
    return order
