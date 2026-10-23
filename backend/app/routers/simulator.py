"""Algorithm simulator: real website orders through the packing algorithm, with vs without."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Order, Product
from ..security import Principal, require_staff
from ..services import feasibility, simulation
from ..services.packer_client import PackerError, PackerUnavailable

router = APIRouter(prefix="/api/sim", tags=["Algorithm simulator"])


class SimLine(BaseModel):
    product_id: int
    quantity: int = Field(1, ge=1, le=20)


class SimCustom(BaseModel):
    items: list[SimLine] = Field(min_length=1, max_length=30)


def _run(db: Session, units: list[dict]) -> dict:
    if not units:
        raise HTTPException(422, "Add at least one product.")
    try:
        return simulation.simulate(db, units)
    except PackerUnavailable as e:
        raise HTTPException(503, f"The packing engine is offline. {e}")
    except PackerError as e:
        raise HTTPException(502, f"The packing engine rejected the request: {e.message}")


@router.get("/orders", summary="Website orders available to simulate (newest first)")
def orders(p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    rows = db.query(Order).order_by(Order.id.desc()).limit(100).all()
    return [{"id": o.id, "code": o.code, "status": o.status, "created_at": o.created_at.isoformat(),
             "units": sum(i.quantity for i in o.items),
             "items": [{"name": i.name, "quantity": i.quantity} for i in o.items]} for o in rows]


@router.get("/products", summary="Catalogue products for custom simulations")
def products(p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    return [{"id": x.id, "name": x.name, "category": x.category, "fragile": x.fragile,
             "dims_cm": [x.length_cm, x.width_cm, x.height_cm], "art": x.art}
            for x in db.query(Product).filter(Product.is_active.is_(True)).order_by(Product.category, Product.name)]


@router.get("/orders/{order_id}", summary="Run the algorithm on one website order and compare")
def simulate_order(order_id: int, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found.")
    units, _ = feasibility.build_units(o)
    res = _run(db, units)
    res["order"] = {"id": o.id, "code": o.code, "status": o.status,
                    "items": [{"name": i.name, "quantity": i.quantity, "product_id": i.product_id,
                               "art": i.product.art if i.product else None} for i in o.items]}
    return res


@router.post("/custom", summary="Run the algorithm on any mix of catalogue products")
def simulate_custom(body: SimCustom, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    units = simulation.units_from_items(db, [ln.model_dump() for ln in body.items])
    res = _run(db, units)
    ids = {u["product_id"] for u in units}
    res["order"] = {"id": None, "code": "Custom mix", "status": None,
                    "items": [{"name": x.name, "quantity": sum(1 for u in units if u["product_id"] == x.id),
                               "product_id": x.id, "art": x.art}
                              for x in db.query(Product).filter(Product.id.in_(ids))]}
    return res


@router.get("/summary", summary="With vs without the algorithm across recent website orders")
def summary(limit: int = 50, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    rows = db.query(Order).order_by(Order.id.desc()).limit(max(1, min(limit, 200))).all()
    tot = {"orders": 0, "algorithm_cm3": 0.0, "single_row_cm3": 0.0, "stock_cm3": 0.0, "stock_orders": 0,
           "algorithm_cost": 0.0, "single_row_cost": 0.0, "stock_cost": 0.0, "algo_cost_on_stock_orders": 0.0,
           "algo_cm3_on_stock_orders": 0.0, "algorithm_void": 0, "stock_void": 0}
    per = []
    try:
        for o in rows:
            units, _ = feasibility.build_units(o)
            if not units:
                continue
            a = simulation.with_algorithm(units)
            r = simulation.single_row(units)
            s = simulation.stock_carton(db, units)
            tot["orders"] += 1
            tot["algorithm_cm3"] += a["volume_cm3"]; tot["single_row_cm3"] += r["volume_cm3"]
            tot["algorithm_cost"] += a["box_cost"]; tot["single_row_cost"] += r["box_cost"]
            tot["algorithm_void"] += a["void_fill_sheets"]
            if s.get("available") and s["box_cost"] is not None:
                tot["stock_orders"] += 1
                tot["stock_cm3"] += s["volume_cm3"]; tot["stock_cost"] += s["box_cost"]
                tot["algo_cm3_on_stock_orders"] += a["volume_cm3"]; tot["algo_cost_on_stock_orders"] += a["box_cost"]
                tot["stock_void"] += s["void_fill_sheets"]
            per.append({"id": o.id, "code": o.code, "units": len(units), "algorithm_cm3": a["volume_cm3"],
                        "single_row_cm3": r["volume_cm3"], "stock_cm3": s.get("volume_cm3"),
                        "stock_carton": s.get("carton"), "algorithm_fill": a["fill"],
                        "stock_fill": s.get("fill"), "algorithm_box_cm": a["box_cm"]})
    except PackerUnavailable as e:
        raise HTTPException(503, f"The packing engine is offline. {e}")
    tot = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in tot.items()}
    return {"totals": tot, "orders": per}
