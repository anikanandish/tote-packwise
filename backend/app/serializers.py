"""Turns database rows into JSON-friendly dicts for API responses."""
from .models import Carton, Material, Order, PackingPlan, Product

PACKAGING_FIELDS = ("length_cm", "width_cm", "height_cm", "weight_g", "fragile", "padding_cm", "orientation",
                    "protection_material_code", "protection_qty_per_unit", "handling_instructions", "restrictions")


def product(p: Product, packaging: bool = False) -> dict:
    d = {"id": p.id, "slug": p.slug, "name": p.name, "brand": p.brand, "description": p.description,
         "category": p.category, "price": p.price, "image_url": p.image_url, "art": p.art, "stock": p.stock,
         "in_stock": p.stock > 0, "rating": p.rating, "rating_count": p.rating_count, "featured": p.featured,
         "is_active": p.is_active, "created_at": p.created_at.isoformat(), "fragile": p.fragile}
    if packaging:
        d["packaging"] = {f: getattr(p, f) for f in PACKAGING_FIELDS}
    return d


def order(o: Order, staff: bool = False) -> dict:
    d = {"id": o.id, "code": o.code, "status": o.status, "created_at": o.created_at.isoformat(),
         "updated_at": o.updated_at.isoformat(), "subtotal": o.subtotal, "shipping": o.shipping,
         "total": o.total, "payment_ref": o.payment_ref, "payment_simulated": True,
         "contact": o.contact, "address": o.address,
         "items": [{"product_id": i.product_id, "name": i.name, "unit_price": i.unit_price, "quantity": i.quantity,
                    "slug": i.product.slug if i.product else None,
                    "art": i.product.art if i.product else None,
                    "image_url": i.product.image_url if i.product else None} for i in o.items],
         "timeline": [{"status": e.status, "note": e.note, "at": e.created_at.isoformat()} for e in o.events]}
    if staff:
        d["priority"] = o.priority
        d["priority_reason"] = o.priority_reason
        d["fragile"] = any(i.product.fragile for i in o.items)
        d["unit_count"] = sum(i.quantity for i in o.items)
        d["weight_g"] = sum(i.product.weight_g * i.quantity for i in o.items)
        d["customer"] = o.user.name if o.user else None
        for i, item in zip(o.items, d["items"]):
            item["packaging"] = {f: getattr(i.product, f) for f in PACKAGING_FIELDS}
    return d


def carton(c: Carton) -> dict:
    nominal = [c.nominal_length_mm, c.nominal_width_mm, c.nominal_height_mm]
    internal = [c.length_mm, c.width_mm, c.height_mm]
    return {"id": c.id, "code": c.code, "name": c.name, "category": c.category,
            "nominal_mm": nominal, "internal_mm": internal, "internal_verified": c.internal_verified,
            "internal_differs": nominal != internal,
            # cm views of the internal size, kept for screens that work in cm
            "length_cm": c.length_cm, "width_cm": c.width_cm, "height_cm": c.height_cm,
            "volume_cm3": round(c.volume_mm3 / 1000, 1), "volume_l": round(c.volume_mm3 / 1_000_000, 3),
            "max_weight_g": c.max_weight_g, "unit_cost": c.unit_cost, "stock": c.stock, "reserved": c.reserved,
            "available": c.stock - c.reserved, "min_stock": c.min_stock, "is_active": c.is_active,
            "is_baseline": c.is_baseline, "is_predefined": c.is_predefined,
            "sample_fields": list(c.sample_fields or []), "notes": c.notes,
            "low_stock": (c.stock - c.reserved) <= c.min_stock,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat()}


def material(m: Material) -> dict:
    return {"id": m.id, "code": m.code, "name": m.name, "unit": m.unit, "stock": m.stock, "reserved": m.reserved,
            "available": m.stock - m.reserved, "min_stock": m.min_stock, "unit_cost": m.unit_cost,
            "is_active": m.is_active, "notes": m.notes, "low_stock": (m.stock - m.reserved) <= m.min_stock,
            "updated_at": m.updated_at.isoformat()}


def plan(p: PackingPlan, full: bool = True) -> dict:
    sel = (p.snapshot or {}).get("selected")
    d = {"id": p.id, "order_id": p.order_id, "order_code": p.order.code if p.order else None, "status": p.status,
         "carton": sel["carton"] if sel else None, "is_override": p.is_override, "parent_plan_id": p.parent_plan_id,
         "estimated_cost": p.estimated_cost, "baseline_cost": p.baseline_cost,
         "estimated_savings": p.estimated_savings, "utilization": p.utilization, "void_cm3": p.void_cm3,
         "carton_volume_cm3": p.carton_volume_cm3, "baseline_volume_cm3": p.baseline_volume_cm3,
         "created_by": p.created_by, "created_at": p.created_at.isoformat(),
         "accepted_by": p.accepted_by, "accepted_at": p.accepted_at.isoformat() if p.accepted_at else None,
         "completed_at": p.completed_at.isoformat() if p.completed_at else None,
         "cancelled_at": p.cancelled_at.isoformat() if p.cancelled_at else None, "cancel_reason": p.cancel_reason,
         "override": (p.snapshot or {}).get("override")}
    if full:
        ev = p.snapshot["evaluation"]
        d.update({
            "selected": sel,
            "units": ev["units"], "totals": ev["totals"], "rules": ev["rules"], "blockers": ev["blockers"],
            "alternatives": ev.get("alternatives", []), "warnings": ev.get("warnings", []),
            "evaluations": [{k: v for k, v in e.items() if k != "placement"} | {"has_placement": e.get("placement") is not None}
                            for e in ev["evaluations"]],
            "baseline": ev["baseline"], "engine": ev["engine"],
            "placements": [{"seq": r.seq, "unit_ref": r.unit_ref, "product_id": r.product_id, "name": r.product_name,
                            "x": r.x_cm, "y": r.y_cm, "z": r.z_cm, "dx": r.dx_cm, "dy": r.dy_cm, "dz": r.dz_cm,
                            "padding_cm": r.padding_cm, "rotated": r.rotated} for r in p.placements],
            "reservations": [{"item_type": r.item_type, "code": r.item_code, "quantity": r.quantity,
                              "status": r.status} for r in p.reservations],
        })
    return d
