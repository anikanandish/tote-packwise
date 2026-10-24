"""Algorithm simulator: replays the packing algorithm on real website orders and compares
it with two ways of packing WITHOUT the algorithm.

  * With the algorithm   - the original packer.cpp design() sweep (every trial recorded).
  * Without: one row     - items placed side by side in order, no rotation, no width search.
  * Without: stock box   - the smallest catalogue carton that holds the items (same safety rules).

All three use the same padded item sizes and the same cost and void-fill rules, so the
comparison is like-for-like. Units in responses: centimetres, cm3, m2, INR.
"""
import math
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Carton
from . import feasibility, packer_client


def _cm(mm: float) -> float:
    return round(mm / 10, 1)


def _placement(p: dict, unit: dict, seq: Optional[int] = None) -> dict:
    """Engine placement (mm) -> view placement (cm), same shape the PackWise views use."""
    return {"unit_ref": unit["ref"], "seq": seq if seq is not None else p.get("seq"), "name": unit["name"],
            "product_id": unit["product_id"], "x": _cm(p["x"]), "y": _cm(p["y"]), "z": 0.0,
            "dx": _cm(p.get("dx", p.get("l"))), "dy": _cm(p.get("dy", p.get("w"))), "dz": _cm(p.get("dz", p.get("h"))),
            "padding_cm": unit["padding_cm"], "rotated": bool(p.get("rotated"))}


def _metrics(dims_cm: list[float], units: list[dict], placements: list[dict], unit_cost: Optional[float] = None) -> dict:
    L, W, H = dims_cm
    vol = L * W * H
    items_vol = sum(u["padded_cm"][0] * u["padded_cm"][1] * u["padded_cm"][2] for u in units)
    floor = sum(p["dx"] * p["dy"] for p in placements)
    board = feasibility.custom_box_cost(dims_cm)
    empty = max(0.0, vol - items_vol)
    sheets = math.ceil(empty / settings.void_fill_cm3_per_unit) if settings.void_fill_cm3_per_unit > 0 else 0
    return {"box_cm": [round(L, 1), round(W, 1), round(H, 1)], "volume_cm3": round(vol, 1),
            "items_volume_cm3": round(items_vol, 1), "empty_cm3": round(empty, 1),
            "fill": round(min(1, items_vol / vol), 4) if vol else None,
            "floor_fill": round(min(1, floor / (L * W)), 4) if L * W else None,
            "board_m2": board["area_m2"],
            "box_cost": unit_cost if unit_cost is not None else board["unit_cost"],
            "cost_rule": "catalogue unit price" if unit_cost is not None else board["rule"],
            "void_fill_sheets": sheets}


def _steps(placements: list[dict]) -> list[dict]:
    steps, row_y, row = [], None, 0
    for p in placements:
        new_row = row_y is None or p["y"] > row_y + 1e-6
        if new_row:
            row += 1
            row_y = p["y"]
        what = []
        if new_row and row > 1:
            what.append(f"row full, so a new row starts {p['y']} cm back")
        what.append(f"placed {p['x']} cm along row {row}")
        if p["rotated"]:
            what.append("turned 90° to fit")
        steps.append({"seq": p["seq"], "ref": p["unit_ref"], "name": p["name"], "row": row,
                      "new_row": new_row and row > 1, "rotated": p["rotated"], "text": "; ".join(what)})
    return steps


def with_algorithm(units: list[dict]) -> dict:
    items = [{"id": u["ref"], "l": u["padded_mm"][0], "w": u["padded_mm"][1], "h": u["padded_mm"][2]} for u in units]
    sw = packer_client.sweep(items)
    by_ref = {u["ref"]: u for u in units}
    placements = [_placement(p, by_ref[p["id"]]) for p in sw["placements"]]
    box = [_cm(sw["box"]["W"]), _cm(sw["box"]["L"]), _cm(sw["box"]["H"])]
    trials = [{"k": t["k"], "width_cm": _cm(t["width"]), "fits": t["fits"],
               **({"box_cm": [_cm(t["W"]), _cm(t["L"]), _cm(t["H"])], "volume_cm3": round(t["volume"] / 1000, 1)}
                  if t["fits"] else {})} for t in sw["trials"]]
    return {"key": "algorithm", "label": "With the algorithm",
            "note": f"Width search: {sw['trial_count']} row widths tried between {_cm(sw['lo'])} and {_cm(sw['hi'])} cm; "
                    f"the best scoring box was kept.",
            "placements": placements, "steps": _steps(placements),
            "sweep": {"lo_cm": _cm(sw["lo"]), "hi_cm": _cm(sw["hi"]), "best": sw["best"],
                      "best_width_cm": _cm(sw["best_width"]), "trials": trials},
            **_metrics(box, units, placements)}


def single_row(units: list[dict]) -> dict:
    """No algorithm: everything side by side in the order it was picked, never rotated."""
    x, placements = 0, []
    for i, u in enumerate(units):
        l, w, h = u["padded_mm"]
        placements.append(_placement({"x": x, "y": 0, "l": l, "w": w, "h": h, "rotated": False}, u, seq=i + 1))
        x += l
    box = [_cm(x), _cm(max(u["padded_mm"][1] for u in units)), _cm(max(u["padded_mm"][2] for u in units))]
    return {"key": "single_row", "label": "Without: one straight row",
            "note": "Items side by side in pick order, no turning, no width search.",
            "placements": placements, **_metrics(box, units, placements)}


def stock_carton(db: Session, units: list[dict]) -> dict:
    """No algorithm choosing the size: the smallest catalogue carton the items fit in."""
    cartons = [c for c in db.query(Carton).filter(Carton.is_active.is_(True)).all()
               if c.code not in (settings.custom_box_code, settings.made_to_measure_code)]
    cartons.sort(key=lambda c: c.volume_mm3)
    weight = sum(u["weight_g"] for u in units)
    candidates = [c for c in cartons if (c.max_weight_g is None or c.max_weight_g >= weight)
                  and not feasibility.dimension_precheck(units, feasibility.carton_snapshot(c))]
    base = {"key": "stock", "label": "Without: smallest stock carton",
            "note": "The smallest catalogue carton a packer could grab that safely holds the items."}
    if not candidates:
        return {**base, "available": False, "reason": "No catalogue carton can hold these items."}
    resp = packer_client.pack_cartons(
        [{"id": u["ref"], "l": u["padded_mm"][0], "w": u["padded_mm"][1], "h": u["padded_mm"][2]} for u in units],
        [{"id": f"C{c.id}", "l": c.length_mm, "w": c.width_mm, "h": c.height_mm} for c in candidates])
    by_ref = {u["ref"]: u for u in units}
    for r in resp["results"]:
        if r["fits"]:
            c = next(c for c in candidates if f"C{c.id}" == r["carton_id"])
            placements = [_placement(p, by_ref[p["id"]]) for p in r["placements"]]
            return {**base, "available": True, "carton": c.name,
                    **_metrics([c.length_cm, c.width_cm, c.height_cm], units, placements, c.unit_cost),
                    "placements": placements}
    return {**base, "available": False, "reason": "No catalogue carton can hold these items in one layer."}


def simulate(db: Session, units: list[dict]) -> dict:
    algo = with_algorithm(units)
    row = single_row(units)
    stock = stock_carton(db, units)
    comparisons = []
    for other in (row, stock):
        if other.get("available", True):
            comparisons.append({"against": other["key"],
                                "volume_saved_cm3": round(other["volume_cm3"] - algo["volume_cm3"], 1),
                                "volume_saved_pct": round(1 - algo["volume_cm3"] / other["volume_cm3"], 4),
                                "board_saved_m2": round(other["board_m2"] - algo["board_m2"], 4),
                                "cost_saved": round((other["box_cost"] or 0) - (algo["box_cost"] or 0), 2),
                                "void_fill_saved": other["void_fill_sheets"] - algo["void_fill_sheets"]})
    return {"units": [{k: u[k] for k in ("ref", "name", "product_id", "dims_cm", "padded_cm", "padding_cm", "fragile",
                                         "weight_g")} for u in units],
            "algorithm": algo, "without": [row, stock], "comparisons": comparisons,
            "assumptions": [
                "All options use the same padded item sizes (fragile items get their protective padding).",
                "Cut-to-size boxes are priced by board area of a regular slotted carton: "
                f"(2L + 2W + 3.5 cm) × (H + W) × ₹{settings.board_cost_per_m2:g}/m² + ₹{settings.box_make_cost:g}.",
                "Stock cartons use their catalogue unit price.",
                f"Void fill: 1 kraft sheet per {settings.void_fill_cm3_per_unit:g} cm³ of empty space (estimate).",
                "The algorithm packs one layer: the tallest item sets the box height in every option.",
            ]}


def units_from_items(db: Session, lines: list[dict]) -> list[dict]:
    """Custom simulation input: [{product_id, quantity}] using real catalogue products."""
    from types import SimpleNamespace
    from ..models import Product
    order_lines = []
    for ln in lines:
        p = db.get(Product, int(ln["product_id"]))
        if p and int(ln.get("quantity", 1)) > 0:
            order_lines.append(SimpleNamespace(product=p, quantity=min(int(ln.get("quantity", 1)), 20)))
    units, _ = feasibility.build_units(SimpleNamespace(items=order_lines))
    return units
