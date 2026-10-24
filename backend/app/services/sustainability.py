"""Illustrative right-size packaging and delivery-impact estimates for checkout."""
import math
from types import SimpleNamespace

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Carton
from . import feasibility, packer_client

# Approximate Pune-to-state route distances (km), used as a demo route lookup.
# International distances are country-level multimodal proxies, not carrier routes.
INDIA_ROUTE_KM = {
    "Andhra Pradesh": 950, "Arunachal Pradesh": 2700, "Assam": 2350, "Bihar": 1650,
    "Chhattisgarh": 950, "Goa": 450, "Gujarat": 650, "Haryana": 1450,
    "Himachal Pradesh": 1700, "Jharkhand": 1450, "Karnataka": 850, "Kerala": 1250,
    "Madhya Pradesh": 700, "Maharashtra": 250, "Manipur": 2700, "Meghalaya": 2500,
    "Mizoram": 2500, "Nagaland": 2600, "Odisha": 1350, "Punjab": 1650, "Rajasthan": 1050,
    "Sikkim": 2100, "Tamil Nadu": 1200, "Telangana": 600, "Tripura": 2500,
    "Uttar Pradesh": 1350, "Uttarakhand": 1600, "West Bengal": 1950,
    "Andaman and Nicobar Islands": 2800, "Chandigarh": 1600,
    "Dadra and Nagar Haveli and Daman and Diu": 450, "Delhi": 1450,
    "Jammu and Kashmir": 2000, "Ladakh": 2450, "Lakshadweep": 700, "Puducherry": 1150,
}
COUNTRY_ROUTE_KM = {
    "United States": 14000, "Canada": 12500, "Australia": 9500,
    "United Kingdom": 7800, "United Arab Emirates": 2500, "Singapore": 3900,
}

# India SFC–TERI 2026 WTW factor for an average diesel small commercial vehicle (<3.5 t GVW).
# https://www.teriin.org/sites/default/files/files/SFC-India-TERI.pdf (Table 4, 0.3795 kgCO2e/tkm)
ROAD_FREIGHT_KGCO2E_PER_TONNE_KM = 0.3795
# Explicitly illustrative material mass assumptions; replace with measured supplier data.
CORRUGATED_BOARD_KG_PER_M2 = 0.55
KRAFT_SHEET_KG = 0.01


def _board_area_m2(dims_cm: list[float]) -> float:
    length, width, height = dims_cm
    return (2 * length + 2 * width + 3.5) * (height + width) / 10000


def estimate(db: Session, cart_lines: list, address: dict) -> dict:
    """Compare the engine's designed box to the configured large-carton baseline.

    This is a non-blocking estimate: a missing baseline or offline packing engine must never
    prevent a customer from placing an order.
    """
    country, state = address.get("country", ""), address.get("state", "")
    if country == "India":
        distance_km = INDIA_ROUTE_KM.get(state)
    else:
        distance_km = COUNTRY_ROUTE_KM.get(country)
    if not distance_km or not cart_lines:
        return {"available": False, "reason": "No route estimate is available for this destination."}

    baseline = db.query(Carton).filter(Carton.is_baseline.is_(True), Carton.is_active.is_(True)).first()
    if not baseline:
        return {"available": False, "reason": "No reference carton is configured."}
    if settings.packing_algorithm == "optimizer":
        return {"available": False, "reason": "The layered optimizer does not expose a design-only estimate."}

    order_stub = SimpleNamespace(items=[SimpleNamespace(product=line.product, quantity=line.quantity)
                                        for line in cart_lines])
    units, _ = feasibility.build_units(order_stub, settings.packing_algorithm)
    engine_items = [{"id": unit["ref"], "l": unit["engine_mm"][0], "w": unit["engine_mm"][1],
                     "h": unit["engine_mm"][2], "fragile": unit["fragile"]} for unit in units]
    algorithm = "optimizer2" if settings.packing_algorithm == "optimizer2" else None
    try:
        design = packer_client.design(engine_items, algorithm)
    except (packer_client.PackerError, packer_client.PackerUnavailable):
        return {"available": False, "reason": "The packing engine was unavailable for this estimate."}

    box = design.get("box", {})
    if not all(isinstance(box.get(dim), (int, float)) and box[dim] > 0 for dim in ("W", "L", "H")):
        return {"available": False, "reason": "The packing engine returned no usable box design."}
    designed_dims_cm = [box["W"] / 10, box["L"] / 10, box["H"] / 10]
    baseline_dims_cm = [baseline.length_mm / 10, baseline.width_mm / 10, baseline.height_mm / 10]
    cardboard_saved_m2 = max(0.0, _board_area_m2(baseline_dims_cm) - _board_area_m2(designed_dims_cm))

    padded_volume_cm3 = sum(unit["padded_cm"][0] * unit["padded_cm"][1] * unit["padded_cm"][2]
                             for unit in units)
    baseline_volume_cm3 = baseline.length_mm * baseline.width_mm * baseline.height_mm / 1000
    designed_volume_cm3 = box["W"] * box["L"] * box["H"] / 1000
    void_fill_per_sheet = settings.void_fill_cm3_per_unit
    if void_fill_per_sheet > 0:
        baseline_sheets = math.ceil(max(0, baseline_volume_cm3 - padded_volume_cm3) / void_fill_per_sheet)
        designed_sheets = math.ceil(max(0, designed_volume_cm3 - padded_volume_cm3) / void_fill_per_sheet)
        kraft_sheets_saved = max(0, baseline_sheets - designed_sheets)
    else:
        kraft_sheets_saved = 0

    packaging_mass_saved_kg = cardboard_saved_m2 * CORRUGATED_BOARD_KG_PER_M2 + kraft_sheets_saved * KRAFT_SHEET_KG
    delivery_co2e_saved_kg = packaging_mass_saved_kg / 1000 * distance_km * ROAD_FREIGHT_KGCO2E_PER_TONNE_KM
    return {
        "available": True,
        "warehouse": "Pune, Maharashtra, India",
        "destination": f"{state}, {country}",
        "distance_km": distance_km,
        "baseline_carton": baseline.code,
        "designed_box_mm": [round(box["W"]), round(box["L"]), round(box["H"])],
        "cardboard_saved_m2": round(cardboard_saved_m2, 4),
        "kraft_sheets_saved": kraft_sheets_saved,
        "packaging_mass_saved_kg": round(packaging_mass_saved_kg, 4),
        "delivery_co2e_saved_kg": round(delivery_co2e_saved_kg, 4),
        "method": "Estimated packaging mass avoided versus the reference carton, multiplied by estimated route distance and the India road-freight factor.",
        "assumptions": {
            "route_distance": "Approximate Pune-to-state distance in India; international routes use a country-level distance proxy.",
            "transport_mode": "Road-freight factor used as an illustrative proxy; international mode and actual carrier route are not known.",
            "road_factor_kgco2e_per_tonne_km": ROAD_FREIGHT_KGCO2E_PER_TONNE_KM,
            "corrugated_board_kg_per_m2": CORRUGATED_BOARD_KG_PER_M2,
            "kraft_sheet_kg": KRAFT_SHEET_KG,
            "kraft_sheet_volume_cm3": void_fill_per_sheet,
            "reference_carton": baseline.code,
            "note": "Illustrative planning estimate, not a carrier measurement. Item-protection materials are unchanged; the saved packing-material figure counts kraft void-fill sheets only.",
        },
    }
