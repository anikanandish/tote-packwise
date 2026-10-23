"""Read-only data feed for the standalone Packing Simulator website (simulator-site/, port 5175).

The website runs the packing algorithm itself, in the browser, with a line-for-line JavaScript
port of packer.cpp. It only needs real data from the TOTE store: products with their packaging
sizes, the stock cartons, the packing rules and recent orders. No customer details are included -
orders are reduced to their code, date, status and item lines.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Carton, Order, Product
from ..services.feasibility import GLUE_FLAP_CM

router = APIRouter(prefix="/api/public", tags=["Public"])


@router.get("/sim-data", summary="Products, cartons, rules and anonymised recent orders for the simulator website")
def sim_data(db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.is_active.is_(True)).order_by(Product.category, Product.name).all()
    cartons = (db.query(Carton).filter(Carton.is_active.is_(True), Carton.code != settings.custom_box_code)
               .order_by(Carton.length_mm * Carton.width_mm * Carton.height_mm).all())
    orders = db.query(Order).order_by(Order.id.desc()).limit(40).all()
    return {
        "source": "TOTE store database",
        "products": [{"id": p.id, "name": p.name, "category": p.category, "art": p.art,
                      "dims_cm": [p.length_cm, p.width_cm, p.height_cm], "weight_g": p.weight_g,
                      "fragile": p.fragile, "padding_cm": p.padding_cm or 0} for p in products],
        "cartons": [{"code": c.code, "name": c.name, "dims_cm": [c.length_cm, c.width_cm, c.height_cm],
                     "max_weight_g": c.max_weight_g, "unit_cost": c.unit_cost} for c in cartons],
        "rules": {"fragile_min_padding_cm": settings.fragile_min_padding_cm,
                  "board_cost_per_m2": settings.board_cost_per_m2, "box_make_cost": settings.box_make_cost,
                  "glue_flap_cm": GLUE_FLAP_CM, "void_fill_cm3_per_unit": settings.void_fill_cm3_per_unit},
        "orders": [{"code": o.code, "status": o.status, "created_at": o.created_at.isoformat(),
                    "items": [{"product_id": i.product_id, "name": i.name, "quantity": i.quantity} for i in o.items]}
                   for o in orders if o.items],
    }
