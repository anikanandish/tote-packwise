"""Admin-only endpoints: products, cartons, materials, stock, reports, history."""
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import serializers as S
from ..database import get_db
from ..models import (AuditEvent, Carton, Material, Order, PackingCompletion, PackingPlan, Product, StockMovement,
                      WorkerOverride)
from ..schemas import (CartonIn, CartonPatch, MaterialIn, MaterialPatch, PriorityIn, ProductIn, ProductPatch,
                       StockAdjustIn)
from ..security import Principal, require_admin
from ..services import audit, inventory, reports

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def _slug(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:100] or "product"
    slug, n = base, 2
    while db.query(Product).filter(Product.slug == slug).first():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _check_material_code(db: Session, code: Optional[str]):
    if code and not db.query(Material).filter(Material.code == code).first():
        raise HTTPException(422, f"Protective material '{code}' does not exist.")


# ------------------------------------------------------------------ products
@router.get("/products", summary="All products including inactive, with packaging metadata")
def products(p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return [S.product(x, packaging=True) for x in db.query(Product).order_by(Product.category, Product.name)]


@router.post("/products", status_code=201, summary="Create a product")
def create_product(body: ProductIn, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    _check_material_code(db, body.protection_material_code)
    data = body.model_dump()
    prod = Product(**data, slug=_slug(db, body.name), art={"shape": "box", "tone": "#D9B88F"})
    db.add(prod)
    db.flush()
    audit.log(db, "product", "created", p.actor, prod.id, name=prod.name)
    db.commit()
    return S.product(prod, packaging=True)


@router.patch("/products/{product_id}", summary="Edit, deactivate or restock a product")
def update_product(product_id: int, body: ProductPatch, p: Principal = Depends(require_admin),
                   db: Session = Depends(get_db)):
    prod = db.get(Product, product_id)
    if not prod:
        raise HTTPException(404, "Product not found.")
    changes = body.model_dump(exclude_unset=True)
    if "protection_material_code" in changes:
        changes["protection_material_code"] = changes["protection_material_code"] or None
        _check_material_code(db, changes["protection_material_code"])
    before = {k: getattr(prod, k) for k in changes}
    for k, v in changes.items():
        setattr(prod, k, v)
    audit.log(db, "product", "updated", p.actor, prod.id, before=before, after=changes)
    db.commit()
    return S.product(prod, packaging=True)


# ------------------------------------------------------------------ cartons & materials
def _crud_create(db, model, body, kind, actor):
    if db.query(model).filter(model.code == body.code).first():
        raise HTTPException(409, f"Code {body.code} already exists.")
    row = model(**body.model_dump())
    db.add(row)
    db.flush()
    if getattr(row, "is_baseline", False):
        db.query(Carton).filter(Carton.id != row.id).update({Carton.is_baseline: False})
    inventory.initial(db, kind, row, actor)
    audit.log(db, kind, "created", actor, row.id, code=row.code)
    db.commit()
    return row


def _crud_patch(db, model, row_id, body, kind, actor):
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(404, f"{kind.title()} not found.")
    changes = body.model_dump(exclude_unset=True)
    clear_cost = changes.pop("clear_unit_cost", False)
    if clear_cost:
        changes["unit_cost"] = None
    before = {k: getattr(row, k) for k in changes}
    for k, v in changes.items():
        setattr(row, k, v)
    if kind == "carton" and changes.get("is_baseline"):
        db.query(Carton).filter(Carton.id != row.id).update({Carton.is_baseline: False})
    audit.log(db, kind, "updated", actor, row.id, code=row.code, before=before, after=changes)
    db.commit()
    return row


def _adjust(db, model, row_id, body, kind, actor):
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(404, f"{kind.title()} not found.")
    try:
        inventory.adjust(db, kind, row.id, body.delta, body.reason, actor)
    except inventory.StockError as e:
        db.rollback()
        raise HTTPException(409, str(e))
    audit.log(db, kind, "stock_adjusted", actor, row.id, code=row.code, delta=body.delta, reason=body.reason)
    db.commit()
    db.refresh(row)
    return row


@router.get("/cartons", summary="Carton catalogue (sizes in mm; volume calculated)")
def list_cartons(include_retired: bool = False, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    q = db.query(Carton)
    rows = q.order_by(Carton.length_mm * Carton.width_mm * Carton.height_mm).all()
    if not include_retired:
        # Cartons retired by an upgrade from an earlier version stay in the database (history points
        # at them) but are hidden unless asked for, or unless an admin switched one back on.
        rows = [c for c in rows if c.is_active or c.category != "Earlier catalogue"]
    usage = dict(db.query(PackingCompletion.carton_id, func.count(PackingCompletion.id))
                 .group_by(PackingCompletion.carton_id).all())
    plans = dict(db.query(PackingPlan.carton_id, func.count(PackingPlan.id)).group_by(PackingPlan.carton_id).all())
    return [S.carton(c) | {"times_used": usage.get(c.id, 0), "plans": plans.get(c.id, 0)} for c in rows]


def _carton_in_use(db: Session, c: Carton) -> int:
    return db.query(PackingPlan).filter(or_(PackingPlan.carton_id == c.id,
                                            PackingPlan.recommended_carton_id == c.id)).count()


@router.post("/cartons", status_code=201, summary="Add a custom carton (sizes in mm)")
def create_carton(body: CartonIn, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(Carton).filter(Carton.code == body.code).first():
        raise HTTPException(409, f"Code {body.code} already exists.")
    data = body.model_dump()
    for axis in ("length", "width", "height"):
        if data[f"{axis}_mm"] is None:
            data[f"{axis}_mm"] = data[f"nominal_{axis}_mm"]
    row = Carton(**data, is_predefined=False, sample_fields=[])
    db.add(row)
    db.flush()
    if row.is_baseline:
        db.query(Carton).filter(Carton.id != row.id).update({Carton.is_baseline: False})
    inventory.initial(db, "carton", row, p.actor, "Opening stock")
    audit.log(db, "carton", "created", p.actor, row.id, code=row.code,
              nominal_mm=[row.nominal_length_mm, row.nominal_width_mm, row.nominal_height_mm])
    db.commit()
    return S.carton(row)


DIM_FIELDS = ("nominal_length_mm", "nominal_width_mm", "nominal_height_mm", "length_mm", "width_mm", "height_mm")


@router.patch("/cartons/{carton_id}", summary="Edit a carton (sizes, weight, cost, threshold, status, baseline)")
def patch_carton(carton_id: int, body: CartonPatch, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(Carton, carton_id)
    if not c:
        raise HTTPException(404, "Carton not found.")
    changes = body.model_dump(exclude_unset=True)
    if changes.pop("clear_unit_cost", False):
        changes["unit_cost"] = None
    if changes.pop("clear_max_weight", False):
        changes["max_weight_g"] = None
    changes = {k: v for k, v in changes.items() if getattr(c, k) != v}
    # Packing in progress reserved this carton with the old size: do not change it under them.
    if c.reserved > 0 and any(k in changes for k in DIM_FIELDS + ("max_weight_g",)):
        raise HTTPException(409, f"{c.reserved} {c.name} reserved for packing in progress. Finish or cancel those "
                                 "plans before changing its size or weight limit.")
    if changes.get("is_active") is False:
        if c.reserved > 0:
            raise HTTPException(409, f"{c.reserved} {c.name} reserved for packing in progress. Finish or cancel those "
                                     "plans before deactivating it.")
        if c.is_baseline:
            raise HTTPException(409, f"{c.name} is the baseline for savings. Choose another baseline carton first.")
    if changes.get("is_baseline") is False and c.is_baseline:
        raise HTTPException(409, "Choose another carton as the baseline instead (there must always be one).")
    if changes.get("is_baseline") and not (changes.get("is_active", c.is_active)):
        raise HTTPException(409, "Only an active carton can be the baseline.")
    before = {k: getattr(c, k) for k in changes}
    for k, v in changes.items():
        setattr(c, k, v)
    # A value an admin enters is no longer sample data.
    c.sample_fields = [f for f in (c.sample_fields or []) if f not in changes]
    if changes.get("is_baseline"):
        db.query(Carton).filter(Carton.id != c.id).update({Carton.is_baseline: False})
    if changes:
        audit.log(db, "carton", "updated", p.actor, c.id, code=c.code, before=before, after=changes)
    db.commit()
    return S.carton(c)


@router.post("/cartons/{carton_id}/adjust", summary="Adjust carton stock (+/-) with a reason")
def adjust_carton(carton_id: int, body: StockAdjustIn, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    row = _adjust(db, Carton, carton_id, body, "carton", p.actor)
    if "stock" in (row.sample_fields or []):
        row.sample_fields = [f for f in row.sample_fields if f != "stock"]
        db.commit()
    return S.carton(row)


@router.delete("/cartons/{carton_id}", summary="Delete an admin-created carton that has never been used")
def delete_carton(carton_id: int, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(Carton, carton_id)
    if not c:
        raise HTTPException(404, "Carton not found.")
    if c.is_predefined:
        raise HTTPException(409, "Standard cartons cannot be deleted. Deactivate it instead.")
    used = _carton_in_use(db, c) + db.query(PackingCompletion).filter(PackingCompletion.carton_id == c.id).count()
    if used or c.reserved:
        raise HTTPException(409, f"{c.name} appears in {used} packing record(s). Deactivate it instead, so order "
                                 "history keeps pointing at it.")
    if c.is_baseline:
        raise HTTPException(409, "This carton is the baseline. Choose another baseline first.")
    db.query(StockMovement).filter(StockMovement.item_type == "carton", StockMovement.item_id == c.id).delete()
    audit.log(db, "carton", "deleted", p.actor, c.id, code=c.code, name=c.name)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/materials", summary="Protective-material catalogue")
def list_materials(p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return [S.material(m) for m in db.query(Material).order_by(Material.name)]


@router.post("/materials", status_code=201, summary="Add a protective material")
def create_material(body: MaterialIn, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return S.material(_crud_create(db, Material, body, "material", p.actor))


@router.patch("/materials/{material_id}", summary="Edit a protective material")
def patch_material(material_id: int, body: MaterialPatch, p: Principal = Depends(require_admin),
                   db: Session = Depends(get_db)):
    return S.material(_crud_patch(db, Material, material_id, body, "material", p.actor))


@router.post("/materials/{material_id}/adjust", summary="Adjust material stock (+/-) with a reason")
def adjust_material(material_id: int, body: StockAdjustIn, p: Principal = Depends(require_admin),
                    db: Session = Depends(get_db)):
    return S.material(_adjust(db, Material, material_id, body, "material", p.actor))


@router.get("/movements", summary="Stock movement history")
def movements(item_type: Optional[str] = None, item_id: Optional[int] = None, limit: int = Query(200, le=1000),
              p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    q = db.query(StockMovement)
    if item_type:
        q = q.filter(StockMovement.item_type == item_type)
    if item_id:
        q = q.filter(StockMovement.item_id == item_id)
    codes = {o.id: o.code for o in db.query(Order.id, Order.code)}
    return [{"id": m.id, "item_type": m.item_type, "item_code": m.item_code, "kind": m.kind,
             "stock_delta": m.stock_delta, "reserved_delta": m.reserved_delta, "stock_after": m.stock_after,
             "reserved_after": m.reserved_after, "reason": m.reason, "plan_id": m.plan_id,
             "order_code": codes.get(m.order_id), "actor": m.actor, "created_at": m.created_at.isoformat()}
            for m in q.order_by(StockMovement.id.desc()).limit(limit)]


# ------------------------------------------------------------------ orders
def _latest_plan(plans: list[PackingPlan]) -> Optional[PackingPlan]:
    """The plan that currently describes the order: completed > accepted > newest other."""
    for status in ("completed", "accepted"):
        hit = [x for x in plans if x.status == status]
        if hit:
            return max(hit, key=lambda x: x.id)
    live = [x for x in plans if x.status not in ("superseded", "cancelled")]
    return max(live or plans, key=lambda x: x.id) if plans else None


@router.get("/orders", summary="All customer orders with their current packing result")
def admin_orders(q: Optional[str] = None, status: Optional[str] = None, carton: Optional[str] = None,
                 packing: Optional[str] = Query(None, description="no_plan | no_fit | override"),
                 date_from: Optional[str] = None, date_to: Optional[str] = None, limit: int = Query(300, le=1000),
                 p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    qry = db.query(Order)
    if q:
        like = f"%{q.strip()}%"
        qry = qry.filter(or_(Order.code.ilike(like), Order.contact["name"].as_string().ilike(like),
                             Order.contact["email"].as_string().ilike(like)))
    if status:
        qry = qry.filter(Order.status == status)
    df, dt = _parse_date(date_from), _parse_date(date_to, end=True)
    if df:
        qry = qry.filter(Order.created_at >= df)
    if dt:
        qry = qry.filter(Order.created_at <= dt)
    orders = qry.order_by(Order.id.desc()).limit(limit).all()
    plans_by_order: dict[int, list[PackingPlan]] = {}
    if orders:
        for pl in db.query(PackingPlan).filter(PackingPlan.order_id.in_([o.id for o in orders])).all():
            plans_by_order.setdefault(pl.order_id, []).append(pl)
    out = []
    for o in orders:
        plans = plans_by_order.get(o.id, [])
        cur = _latest_plan(plans)
        sel = (cur.snapshot or {}).get("selected") if cur else None
        row = {"id": o.id, "code": o.code, "status": o.status, "created_at": o.created_at.isoformat(),
               "customer": (o.contact or {}).get("name"), "total": o.total, "priority": o.priority,
               "units": sum(i.quantity for i in o.items), "lines": len(o.items),
               "fragile": any(i.product.fragile for i in o.items),
               "plan": None if not cur else {"id": cur.id, "status": cur.status, "is_override": cur.is_override,
                                             "carton_code": sel["carton"]["code"] if sel else None,
                                             "carton_name": sel["carton"]["name"] if sel else None,
                                             "estimated_cost": cur.estimated_cost, "utilization": cur.utilization},
               "plan_count": len(plans), "has_override": any(x.is_override for x in plans)}
        out.append(row)
    if carton:
        out = [r for r in out if r["plan"] and r["plan"]["carton_code"] == carton]
    if packing == "no_plan":
        out = [r for r in out if not r["plan"]]
    elif packing == "no_fit":
        out = [r for r in out if r["plan"] and r["plan"]["status"] == "no_fit"]
    elif packing == "override":
        out = [r for r in out if r["has_override"]]
    return out


@router.get("/orders/{order_id}", summary="One order: items, timeline, every packing plan, overrides, completion")
def admin_order(order_id: int, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found.")
    plans = db.query(PackingPlan).filter(PackingPlan.order_id == o.id).order_by(PackingPlan.id).all()
    cur = _latest_plan(plans)
    comp = db.query(PackingCompletion).filter(PackingCompletion.order_id == o.id).first()
    ovs = db.query(WorkerOverride).filter(WorkerOverride.order_id == o.id).order_by(WorkerOverride.id).all()
    events = db.query(AuditEvent).filter(AuditEvent.order_id == o.id).order_by(AuditEvent.id).all()
    return {
        "order": S.order(o, staff=True) | {"customer_email": (o.contact or {}).get("email")},
        "current_plan_id": cur.id if cur else None,
        "plans": [S.plan(x, full=False) for x in plans],
        "completion": None if not comp else {
            "plan_id": comp.plan_id, "carton_code": comp.carton_code, "materials_used": comp.materials_used,
            "actual_cost": comp.actual_cost, "baseline_cost": comp.baseline_cost, "actual_savings": comp.actual_savings,
            "checklist": comp.checklist, "notes": comp.notes, "actor": comp.actor, "created_at": comp.created_at.isoformat()},
        "overrides": [{"id": x.id, "from": x.original_carton_code, "to": x.selected_carton_code, "reason": x.reason,
                       "actor": x.actor, "original_plan_id": x.original_plan_id, "new_plan_id": x.new_plan_id,
                       "created_at": x.created_at.isoformat()} for x in ovs],
        "audit": [{"id": e.id, "action": e.action, "actor": e.actor, "details": e.details,
                   "created_at": e.created_at.isoformat()} for e in events],
    }


@router.post("/orders/{order_id}/priority", summary="Mark / unmark an order as priority (reason kept)")
def set_priority(order_id: int, body: PriorityIn, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found.")
    o.priority = body.priority
    o.priority_reason = body.reason
    audit.log(db, "order", "priority_set" if body.priority else "priority_cleared", p.actor, o.id, o.id,
              reason=body.reason)
    db.commit()
    return {"id": o.id, "priority": o.priority, "priority_reason": o.priority_reason}


# ------------------------------------------------------------------ dashboard / reports / history
@router.get("/dashboard", summary="Admin dashboard metrics (all derived from stored records)")
def dashboard(p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return reports.dashboard(db)


def _parse_date(s: Optional[str], end: bool = False) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(422, "Dates must be YYYY-MM-DD.")
    return d.replace(hour=23, minute=59, second=59) if end and len(s) == 10 else d


@router.get("/reports", summary="Cost, utilization and packaging-volume report")
def report(date_from: Optional[str] = None, date_to: Optional[str] = None, carton: Optional[str] = None,
           q: Optional[str] = None, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return reports.report(db, _parse_date(date_from), _parse_date(date_to, end=True), carton or None, q or None)


@router.get("/history", summary="Searchable packing-plan history")
def history(q: Optional[str] = None, status: Optional[str] = None, worker: Optional[str] = None,
            carton: Optional[str] = None, override: Optional[bool] = None, date_from: Optional[str] = None,
            date_to: Optional[str] = None, limit: int = Query(200, le=500),
            p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    qry = db.query(PackingPlan).join(Order)
    if q:
        qry = qry.filter(Order.code.ilike(f"%{q.strip()}%"))
    if status:
        qry = qry.filter(PackingPlan.status == status)
    if worker:
        like = f"%{worker}%"
        qry = qry.filter(or_(PackingPlan.created_by.ilike(like), PackingPlan.accepted_by.ilike(like)))
    if carton:
        qry = qry.join(Carton, PackingPlan.carton_id == Carton.id).filter(Carton.code == carton)
    if override is not None:
        qry = qry.filter(PackingPlan.is_override.is_(override))
    df, dt = _parse_date(date_from), _parse_date(date_to, end=True)
    if df:
        qry = qry.filter(PackingPlan.created_at >= df)
    if dt:
        qry = qry.filter(PackingPlan.created_at <= dt)
    return [S.plan(pl, full=False) for pl in qry.order_by(PackingPlan.id.desc()).limit(limit)]


@router.get("/audit", summary="Audit log")
def audit_log(action: Optional[str] = None, limit: int = Query(200, le=1000),
              p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    q = db.query(AuditEvent)
    if action:
        q = q.filter(AuditEvent.action == action)
    codes = {o.id: o.code for o in db.query(Order.id, Order.code)}
    return [{"id": e.id, "entity": e.entity, "entity_id": e.entity_id, "order_code": codes.get(e.order_id),
             "action": e.action, "actor": e.actor, "details": e.details, "created_at": e.created_at.isoformat()}
            for e in q.order_by(AuditEvent.id.desc()).limit(limit)]


@router.get("/overrides", summary="Worker overrides with reasons")
def overrides(p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    codes = {o.id: o.code for o in db.query(Order.id, Order.code)}
    return [{"id": o.id, "order_code": codes.get(o.order_id), "original_plan_id": o.original_plan_id,
             "new_plan_id": o.new_plan_id, "from": o.original_carton_code, "to": o.selected_carton_code,
             "reason": o.reason, "actor": o.actor, "original_cost": o.original_cost, "new_cost": o.new_cost,
             "original_utilization": o.original_utilization, "new_utilization": o.new_utilization,
             "created_at": o.created_at.isoformat()} for o in db.query(WorkerOverride).order_by(WorkerOverride.id.desc())]


@router.get("/settings", summary="Packing rules, baseline carton and engine capabilities (read-only)")
def settings_view(p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    from ..config import settings
    from ..services import packer_client
    baseline = db.query(Carton).filter(Carton.is_baseline.is_(True)).first()
    try:
        engine = packer_client.health()
    except packer_client.PackerUnavailable as e:
        engine = {"status": "unavailable", "error": str(e)}
    return {
        "packer_url": settings.packer_url,
        "engine": engine,
        "baseline_carton": S.carton(baseline) if baseline else None,
        "rules": {
            "fragile_min_padding_cm": settings.fragile_min_padding_cm,
            "void_fill_material_code": settings.void_fill_material_code,
            "void_fill_cm3_per_unit": settings.void_fill_cm3_per_unit,
            "rounding": "Product sizes rounded up, carton sizes rounded down, to whole millimetres",
            "selection": "Smallest active carton (by internal volume) that passes every check; ties broken by lower cost",
            "units": "Carton sizes are stored in whole millimetres; internal dimensions are used for fitting",
            "weight": "Checked only for cartons with a configured maximum weight; otherwise shown as not checked",
            "layout": "Inside each carton the packing algorithm tries 200 row widths in both floor orientations and keeps the tightest layout that fits",
        },
        "worker_code_configured": bool(settings.worker_code),
        "admin_code_configured": bool(settings.admin_access_code),   # the code itself is never returned
        "session_hours": settings.session_hours,
        "currency": settings.currency,
    }
