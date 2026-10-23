"""Dashboard and report calculations. Every number comes from stored records.

Savings are counted once per order: only PackingCompletion rows (unique per
order) feed "actual" figures, and only the single newest open plan per order
feeds "estimated" figures, so regenerated or retried plans never double count.
"""
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (AuditEvent, Carton, Material, Order, PackingCompletion, PackingPlan, WorkerOverride)


def _sum(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals), 2) if vals else None


def _avg(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def low_stock(db: Session) -> list[dict]:
    alerts = []
    for kind, model in (("carton", Carton), ("material", Material)):
        for row in db.query(model).filter(model.is_active.is_(True)).all():
            available = row.stock - row.reserved
            if available <= row.min_stock:
                alerts.append({"type": kind, "id": row.id, "code": row.code, "name": row.name,
                               "stock": row.stock, "reserved": row.reserved, "available": available,
                               "min_stock": row.min_stock, "out": available <= 0})
    return alerts


def open_plans(db: Session) -> list[PackingPlan]:
    """Newest recommended/accepted plan for each order that is not yet packed."""
    rows = (db.query(PackingPlan).join(Order)
            .filter(PackingPlan.status.in_(("recommended", "accepted")),
                    Order.status.in_(("placed", "awaiting_packing", "packing_in_progress")))
            .order_by(PackingPlan.id.desc()).all())
    seen, out = set(), []
    for p in rows:
        if p.order_id not in seen:
            seen.add(p.order_id)
            out.append(p)
    return out


def completion_rows(db: Session, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
                    carton: Optional[str] = None, code: Optional[str] = None):
    q = db.query(PackingCompletion, PackingPlan, Order).join(PackingPlan, PackingCompletion.plan_id == PackingPlan.id) \
        .join(Order, PackingCompletion.order_id == Order.id)
    if date_from:
        q = q.filter(PackingCompletion.created_at >= date_from)
    if date_to:
        q = q.filter(PackingCompletion.created_at <= date_to)
    if carton:
        q = q.filter(PackingCompletion.carton_code == carton)
    if code:
        q = q.filter(Order.code.ilike(f"%{code.strip()}%"))
    return q.order_by(PackingCompletion.created_at.desc()).all()


def dashboard(db: Session) -> dict:
    status_counts = Counter(s for (s,) in db.query(Order.status).all())
    plans_open = open_plans(db)
    with_open_plan = {p.order_id for p in plans_open}
    awaiting_orders = db.query(Order).filter(Order.status.in_(("placed", "awaiting_packing"))).all()
    comps = completion_rows(db)

    actual_costs = [c.actual_cost for c, _, _ in comps]
    savings = [c.actual_savings for c, _, _ in comps]
    utils = [p.utilization for _, p, _ in comps]
    voids = [p.void_cm3 for _, p, _ in comps]
    vol_red = [(p.baseline_volume_cm3 - p.carton_volume_cm3) for _, p, _ in comps
               if p.baseline_volume_cm3 is not None and p.carton_volume_cm3 is not None]

    by_day = defaultdict(lambda: {"orders": 0, "cost": 0.0, "savings": 0.0})
    for c, _, _ in comps:
        d = c.created_at.strftime("%Y-%m-%d")
        by_day[d]["orders"] += 1
        by_day[d]["cost"] += c.actual_cost or 0
        by_day[d]["savings"] += c.actual_savings or 0
    carton_mix = Counter(c.carton_code for c, _, _ in comps)

    failures = (db.query(AuditEvent).filter(AuditEvent.action.in_(("no_fit", "recommendation_failed",
                                                                   "accept_failed", "override_rejected")))
                .order_by(AuditEvent.id.desc()).limit(10).all())
    overrides = db.query(WorkerOverride).order_by(WorkerOverride.id.desc()).limit(10).all()
    order_codes = {o.id: o.code for o in db.query(Order.id, Order.code).all()}
    recent = db.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(15).all()

    cartons = db.query(Carton).filter(Carton.is_active.is_(True)).all()
    cartons.sort(key=lambda c: c.volume_mm3)
    standard = db.query(Carton).filter(Carton.is_predefined.is_(True)).all()
    return {
        "carton_stock": [{"id": c.id, "code": c.code, "name": c.name, "stock": c.stock, "reserved": c.reserved,
                          "available": c.stock - c.reserved, "min_stock": c.min_stock,
                          "low": (c.stock - c.reserved) <= c.min_stock,
                          "sample_stock": "stock" in (c.sample_fields or [])} for c in cartons],
        "data_quality": {
            "standard_cartons": len(standard),
            "unverified_internal": sum(1 for c in standard if not c.internal_verified),
            "no_max_weight": sum(1 for c in cartons if c.max_weight_g is None),
            "sample_values": sum(1 for c in cartons if c.sample_fields),
            "no_price": sum(1 for c in cartons if c.unit_cost is None),
        },
        "orders": {
            "total": sum(status_counts.values()),
            "by_status": dict(status_counts),
            "awaiting_packing": len(awaiting_orders),
            "awaiting_recommendation": sum(1 for o in awaiting_orders if o.id not in with_open_plan),
            "in_progress": status_counts.get("packing_in_progress", 0),
            "packed": sum(status_counts.get(s, 0) for s in ("packed", "ready_for_dispatch", "dispatched")),
            "fragile_open": sum(1 for o in awaiting_orders if any(i.product.fragile for i in o.items)),
            "priority_open": sum(1 for o in awaiting_orders if o.priority),
        },
        "completed": {
            "count": len(comps),
            "actual_cost_total": _sum(actual_costs),
            "actual_cost_avg": _avg(actual_costs),
            "savings_total": _sum(savings),
            "savings_comparable_orders": sum(1 for s in savings if s is not None),
            "avg_utilization": _avg(utils),
            "avg_void_cm3": _avg(voids),
            "volume_reduction_cm3_total": _sum(vol_red),
        },
        "pending": {
            "plans": len(plans_open),
            "estimated_cost_total": _sum(p.estimated_cost for p in plans_open),
            "estimated_savings_total": _sum(p.estimated_savings for p in plans_open),
        },
        "low_stock": low_stock(db),
        "series": {"by_day": [{"date": d, **v} for d, v in sorted(by_day.items())],
                   "carton_mix": [{"carton": k, "count": v} for k, v in carton_mix.most_common()]},
        "failures": [{"id": e.id, "action": e.action, "order_code": order_codes.get(e.order_id), "actor": e.actor,
                      "details": e.details, "created_at": e.created_at.isoformat()} for e in failures],
        "no_fit_count": db.query(PackingPlan).filter(PackingPlan.status == "no_fit").count(),
        "overrides": [{"id": o.id, "order_code": order_codes.get(o.order_id), "from": o.original_carton_code,
                       "to": o.selected_carton_code, "reason": o.reason, "actor": o.actor,
                       "original_cost": o.original_cost, "new_cost": o.new_cost,
                       "created_at": o.created_at.isoformat()} for o in overrides],
        "recent_activity": [{"id": e.id, "entity": e.entity, "action": e.action, "actor": e.actor,
                             "order_code": order_codes.get(e.order_id), "created_at": e.created_at.isoformat()}
                            for e in recent],
    }


def _board_m2(dims_cm) -> Optional[float]:
    """ESTIMATE: corrugated board in a regular slotted carton blank, (2L + 2W + 3.5) x (H + W)."""
    if not dims_cm:
        return None
    from .feasibility import custom_box_cost
    return custom_box_cost(dims_cm)["area_m2"]


def report(db: Session, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
           carton: Optional[str] = None, code: Optional[str] = None) -> dict:
    comps = completion_rows(db, date_from, date_to, carton, code)
    rows, materials = [], defaultdict(lambda: {"quantity": 0, "cost": 0.0, "unit": ""})
    for c, p, o in comps:
        sel = p.snapshot.get("selected") or {}
        rows.append({
            "order_code": o.code, "plan_id": p.id, "completed_at": c.created_at.isoformat(), "actor": c.actor,
            "carton": c.carton_code, "carton_volume_cm3": p.carton_volume_cm3,
            "product_volume_cm3": p.snapshot["evaluation"]["totals"]["product_volume_cm3"],
            "utilization": p.utilization, "void_cm3": p.void_cm3,
            "estimated_cost": p.estimated_cost, "actual_cost": c.actual_cost,
            "baseline_carton": (p.snapshot["evaluation"]["baseline"].get("carton") or {}).get("code"),
            "baseline_cost": c.baseline_cost, "savings": c.actual_savings,
            "baseline_volume_cm3": p.baseline_volume_cm3,
            "volume_reduction_cm3": (round(p.baseline_volume_cm3 - p.carton_volume_cm3, 1)
                                     if p.baseline_volume_cm3 is not None and p.carton_volume_cm3 is not None else None),
            "override": p.is_override, "materials": c.materials_used,
            "carton_name": (sel.get("carton") or {}).get("name"),
            "sample_priced": "unit_cost" in ((sel.get("carton") or {}).get("sample_fields") or []),
            "board_m2_est": _board_m2((sel.get("carton") or {}).get("dims_cm")),
            "baseline_board_m2_est": _board_m2((p.snapshot["evaluation"]["baseline"].get("carton") or {}).get("dims_cm"))
            if p.baseline_volume_cm3 is not None else None,
            "unit_count": sel and p.snapshot["evaluation"]["totals"]["unit_count"],
        })
        for m in c.materials_used:
            materials[m["name"]]["quantity"] += m["quantity"]
            materials[m["name"]]["unit"] = m["unit"]
            if m["unit_cost"] is not None:
                materials[m["name"]]["cost"] += m["quantity"] * m["unit_cost"]

    return {
        "rows": rows,
        "totals": {
            "orders": len(rows),
            "actual_cost": _sum(r["actual_cost"] for r in rows),
            "estimated_cost": _sum(r["estimated_cost"] for r in rows),
            "baseline_cost": _sum(r["baseline_cost"] for r in rows if r["savings"] is not None),
            "savings": _sum(r["savings"] for r in rows),
            "comparable_orders": sum(1 for r in rows if r["savings"] is not None),
            "carton_volume_cm3": _sum(r["carton_volume_cm3"] for r in rows),
            "product_volume_cm3": _sum(r["product_volume_cm3"] for r in rows),
            "volume_reduction_cm3": _sum(r["volume_reduction_cm3"] for r in rows),
            "avg_utilization": _avg(r["utilization"] for r in rows),
        },
        "materials": [{"name": k, **v, "cost": round(v["cost"], 2)} for k, v in materials.items()],
        "carton_usage": _carton_usage(rows),
        "sustainability": {
            "calculated": {
                "carton_volume_cm3": _sum(r["carton_volume_cm3"] for r in rows),
                "baseline_volume_cm3": _sum(r["baseline_volume_cm3"] for r in rows if r["volume_reduction_cm3"] is not None),
                "volume_reduction_cm3": _sum(r["volume_reduction_cm3"] for r in rows),
                "comparable_orders": sum(1 for r in rows if r["volume_reduction_cm3"] is not None),
            },
            "estimated": {
                "void_cm3": _sum(r["void_cm3"] for r in rows),
                "board_m2": _sum(r["board_m2_est"] for r in rows),
                "baseline_board_m2": _sum(r["baseline_board_m2_est"] for r in rows if r["baseline_board_m2_est"] is not None),
                "void_fill_sheets": sum(m["quantity"] for r in rows for m in r["materials"]
                                        if m.get("code") == "KRAFT"),
            },
        },
        "sample_priced_orders": sum(1 for r in rows if r["sample_priced"]),
        "assumptions": [
            "Product volumes use simplified bounding boxes from product packaging metadata.",
            "Utilization = product bounding-box volume ÷ carton internal volume.",
            "Void space = carton internal volume − product bounding-box volume (estimate).",
            "Void-fill paper is an estimate from a configurable rule; actual usage is recorded by the worker.",
            "Baseline = the carton flagged as baseline in the catalogue, priced with the same per-unit costs "
            "and only when it can physically hold the same order.",
            "Costs are frozen in each plan's snapshot; later catalogue price changes do not alter past rows.",
            "Volume avoided = baseline carton volume − selected carton volume, for orders the baseline could also hold "
            "(calculated from internal dimensions).",
            "Cardboard area is an ESTIMATE from the regular slotted carton blank formula (2L + 2W + 3.5 cm) × (H + W); "
            "real cartons vary by style and supplier.",
            "Where a carton's price is still marked as SAMPLE, the cost and savings figures that use it are sample "
            "figures too.",
            "Carton internal dimensions marked 'not verified' are the nominal sizes; fitting used those values.",
            "No CO₂ or emissions figures are calculated.",
        ],
    }


def _carton_usage(rows: list[dict]) -> list[dict]:
    agg = defaultdict(lambda: {"orders": 0, "volume_cm3": 0.0, "cost": 0.0, "name": None})
    for r in rows:
        a = agg[r["carton"]]
        a["orders"] += 1
        a["name"] = r.get("carton_name") or r["carton"]
        a["volume_cm3"] += r["carton_volume_cm3"] or 0
        a["cost"] += r["actual_cost"] or 0
    return sorted(({"code": k, **v, "volume_cm3": round(v["volume_cm3"], 1), "cost": round(v["cost"], 2)}
                   for k, v in agg.items()), key=lambda x: -x["orders"])
