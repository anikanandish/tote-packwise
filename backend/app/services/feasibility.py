"""Carton feasibility and selection layer around the C++ packing engine.

Pipeline for one order:
  1. Expand order lines into physical units and apply padding rules.
  2. For every carton: active? dimension/orientation pre-check, weight limit.
  3. Ask the C++ engine (one HTTP call) to place the units in every carton that
     passed step 2, plus the baseline carton.
  4. Check carton stock and protective-material availability.
  5. Price each feasible carton; choose the smallest (tie-break: lower cost).
  6. Price the baseline carton on the same basis for the savings estimate.

Carton choice: the warehouse stocks six fixed carton sizes. For each carton the C++
engine runs the original width search (pack() at 200 row widths up to the carton's
side, both floor orientations) and keeps the tightest layout that fits. Among the
cartons that pass every check, the SMALLEST (least volume, so least air shipped) is
chosen; a tie on volume goes to the cheaper carton.

Units: the engine works in integer millimetres. Product dimensions are rounded
UP to the next millimetre and carton dimensions DOWN, so rounding can only make
a recommendation more conservative.
"""
import math
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Carton, Material, Order
from . import packer_client


def mm_up(cm: float) -> int:
    return math.ceil(round(cm * 10, 4))


def mm_down(cm: float) -> int:
    return math.floor(round(cm * 10, 4))


# Both optimizers put a fixed cushion around every fragile item (mm added per dimension):
#   optimizer  (original/optimizer.cpp):  CUSHION_TOTAL = 30 -> 15 mm on each side
#   optimizer2 (original/optimizer2.cpp): CUSION_TOTAL  = 15 -> 7.5 mm on each side
# The engine adds it itself, so fragile items are sent WITHOUT padding; these values only
# describe what the engine did.
ENGINE_CUSHION_TOTAL_MM = {"optimizer": 30, "optimizer2": 15}


def optimizer_on() -> bool:
    """True for the layered optimizer (the only algorithm that stacks)."""
    return settings.packing_algorithm == "optimizer"


def fmt(cm: float) -> str:
    return f"{cm:.1f}"


# ----------------------------------------------------------------- units
def build_units(order: Order, algorithm: str = "original") -> tuple[list[dict], list[str]]:
    """Returns (units, order-level blockers). algorithm="optimizer" uses the optimizer's fixed
    fragile cushion; the simulator and health check keep calling this with the original rules."""
    units, blockers = [], []
    for line in order.items:
        p = line.product
        padding = p.padding_cm or 0.0
        padding_rule = "product"
        if p.fragile and padding < settings.fragile_min_padding_cm:
            padding = settings.fragile_min_padding_cm
            padding_rule = "fragile_minimum"
        if p.fragile and not p.protection_material_code:
            blockers.append(f"{p.name} is fragile but has no protective material configured. "
                            "An admin must set one before it can be packed.")
        cushion_total = ENGINE_CUSHION_TOTAL_MM.get(algorithm)
        engine_cushion = cushion_total is not None and p.fragile
        if engine_cushion:
            # the optimizer's own rule replaces the product padding for fragile items
            padding = cushion_total / 20
            padding_rule = f"{algorithm}_fragile_cushion"
        for k in range(line.quantity):
            pl, pw, ph = p.length_cm + 2 * padding, p.width_cm + 2 * padding, p.height_cm + 2 * padding
            bare_mm = [mm_up(p.length_cm), mm_up(p.width_cm), mm_up(p.height_cm)]
            units.append({
                "ref": f"P{p.id}-{k + 1}",
                "product_id": p.id,
                "name": p.name,
                "unit_index": k + 1,
                "quantity_of_line": line.quantity,
                "dims_cm": [p.length_cm, p.width_cm, p.height_cm],
                "padding_cm": padding,
                "padding_rule": padding_rule,
                "padded_cm": [round(pl, 2), round(pw, 2), round(ph, 2)],
                "padded_mm": ([d + cushion_total for d in bare_mm] if engine_cushion
                              else [mm_up(pl), mm_up(pw), mm_up(ph)]),
                # what is sent to the engine: the optimizer adds the fragile cushion itself
                "engine_mm": bare_mm if engine_cushion else [mm_up(pl), mm_up(pw), mm_up(ph)],
                "weight_g": p.weight_g,
                "fragile": p.fragile,
                "orientation": p.orientation,
                "protection_material_code": p.protection_material_code,
                "protection_qty_per_unit": p.protection_qty_per_unit,
                "handling_instructions": p.handling_instructions,
                "restrictions": p.restrictions,
            })
    return units, blockers


def protection_requirements(units: list[dict]) -> dict[str, int]:
    req: dict[str, int] = defaultdict(int)
    for u in units:
        if u["protection_material_code"] and u["protection_qty_per_unit"] > 0:
            req[u["protection_material_code"]] += u["protection_qty_per_unit"]
    return dict(req)


def carton_snapshot(c: Carton) -> dict:
    """Frozen copy of a carton for a plan. dims_mm are the INTERNAL dimensions used for fitting."""
    return {"id": c.id, "code": c.code, "name": c.name, "category": c.category,
            "dims_cm": [c.length_cm, c.width_cm, c.height_cm],
            "dims_mm": [c.length_mm, c.width_mm, c.height_mm],
            "nominal_mm": [c.nominal_length_mm, c.nominal_width_mm, c.nominal_height_mm],
            "internal_verified": c.internal_verified,
            "volume_cm3": round(c.volume_mm3 / 1000, 1),
            "max_weight_g": c.max_weight_g, "unit_cost": c.unit_cost,
            "sample_fields": list(c.sample_fields or []), "is_predefined": c.is_predefined,
            "stock": c.stock, "reserved": c.reserved, "available": c.stock - c.reserved,
            "is_active": c.is_active, "is_baseline": c.is_baseline}


# ----------------------------------------------------------------- checks
def dimension_precheck(units: list[dict], snap: dict) -> list[str]:
    L, W, H = snap["dims_mm"]
    problems = []
    for u in units:
        a, b, h = u["padded_mm"]
        dims = " × ".join(fmt(d) for d in u["padded_cm"])
        label = (f"{u['name']} (with {fmt(u['padding_cm'])} cm padding: {dims} cm)" if u["padding_cm"] > 0
                 else f"{u['name']} ({dims} cm)")
        if h > H:
            note = ("it must stay upright" if u["orientation"] == "upright"
                    else "the packing engine only plans upright placements and never tips items over")
            problems.append(f"{label} is taller than the {fmt(snap['dims_cm'][2])} cm internal height; {note}.")
        elif not ((a <= L and b <= W) or (b <= L and a <= W)):
            problems.append(f"{label} footprint does not fit the "
                            f"{fmt(snap['dims_cm'][0])} × {fmt(snap['dims_cm'][1])} cm floor in either rotation.")
    # report each product once
    seen, unique = set(), []
    for msg in problems:
        key = msg.split(" (")[0]
        if key not in seen:
            seen.add(key)
            unique.append(msg)
    return unique


def void_fill_estimate(carton_volume: float, units: list[dict], materials: dict[str, Material]) -> Optional[dict]:
    code = settings.void_fill_material_code
    mat = materials.get(code)
    if not mat or not mat.is_active:
        return None
    padded_vol = sum(u["padded_cm"][0] * u["padded_cm"][1] * u["padded_cm"][2] for u in units)
    empty = max(0.0, carton_volume - padded_vol)
    qty = math.ceil(empty / settings.void_fill_cm3_per_unit) if settings.void_fill_cm3_per_unit > 0 else 0
    return {"code": code, "quantity": qty, "empty_cm3": round(empty, 1),
            "rule": f"ceil(empty carton volume ÷ {settings.void_fill_cm3_per_unit:g} cm³ per {mat.unit})",
            "estimate": True}


def material_plan(units: list[dict], carton_volume: float, materials: dict[str, Material]) -> list[dict]:
    lines = []
    for code, qty in protection_requirements(units).items():
        m = materials.get(code)
        lines.append({"code": code, "name": m.name if m else code, "unit": m.unit if m else "unit",
                      "quantity": qty, "purpose": "protection", "estimate": False,
                      "rule": "per-unit requirement from product packaging metadata",
                      "unit_cost": m.unit_cost if m else None,
                      "exists": m is not None, "active": bool(m and m.is_active),
                      "available": (m.stock - m.reserved) if m else 0})
    vf = void_fill_estimate(carton_volume, units, materials)
    if vf and vf["quantity"] > 0:
        m = materials[vf["code"]]
        existing = next((ln for ln in lines if ln["code"] == vf["code"]), None)
        if existing:
            existing["quantity"] += vf["quantity"]
            existing["estimate"] = True
            existing["rule"] += f" + void fill {vf['rule']}"
        else:
            lines.append({"code": m.code, "name": m.name, "unit": m.unit, "quantity": vf["quantity"],
                          "purpose": "void_fill", "estimate": True, "rule": vf["rule"],
                          "unit_cost": m.unit_cost, "exists": True, "active": m.is_active,
                          "available": m.stock - m.reserved})
    return lines


def price(carton_cost: Optional[float], mat_lines: list[dict]) -> dict:
    missing = []
    if carton_cost is None:
        missing.append("carton unit cost")
    total = carton_cost or 0.0
    breakdown = [{"label": "Carton", "amount": carton_cost}]
    for ln in mat_lines:
        amt = None if ln["unit_cost"] is None else round(ln["unit_cost"] * ln["quantity"], 2)
        if amt is None:
            missing.append(f"{ln['name']} unit cost")
        else:
            total += amt
        breakdown.append({"label": f"{ln['name']} × {ln['quantity']}", "amount": amt,
                          "unit_cost": ln["unit_cost"], "estimate": ln["estimate"]})
    return {"total": None if missing else round(total, 2), "breakdown": breakdown, "missing": missing}


# ----------------------------------------------------------------- board cost (simulator comparisons)
GLUE_FLAP_CM = 3.5


def custom_box_cost(dims_cm: list[float]) -> dict:
    """Board for a regular slotted carton: blank = (2L + 2W + glue flap) x (H + W)."""
    L, W, H = dims_cm
    area_m2 = (2 * L + 2 * W + GLUE_FLAP_CM) * (H + W) / 10000
    cost = round(area_m2 * settings.board_cost_per_m2 + settings.box_make_cost, 2)
    return {"area_m2": round(area_m2, 4), "unit_cost": cost,
            "rule": f"board {area_m2:.3f} m² × ₹{settings.board_cost_per_m2:g}/m² + ₹{settings.box_make_cost:g} per box"}


# ----------------------------------------------------------------- main entry
def evaluate(db: Session, order: Order, only_carton_id: Optional[int] = None) -> dict:
    units, blockers = build_units(order, settings.packing_algorithm)
    materials = {m.code: m for m in db.query(Material).all()}
    all_cartons = db.query(Carton).order_by(Carton.unit_cost.is_(None), Carton.unit_cost, Carton.id).all()
    # Retired cartons from earlier versions are left out; switched-off standard cartons are listed.
    cartons = [c for c in all_cartons if c.code not in (settings.custom_box_code, settings.made_to_measure_code)
               and (c.is_active or c.is_predefined or c.is_baseline)]
    mtm_carton = next((c for c in all_cartons if c.code == settings.made_to_measure_code), None)
    baseline = next((c for c in cartons if c.is_baseline), None)

    product_volume = sum(u["dims_cm"][0] * u["dims_cm"][1] * u["dims_cm"][2] for u in units)
    padded_volume = sum(u["padded_cm"][0] * u["padded_cm"][1] * u["padded_cm"][2] for u in units)
    total_weight = sum(u["weight_g"] for u in units)

    # order-level material existence check
    for code in protection_requirements(units):
        m = materials.get(code)
        if not m:
            blockers.append(f"Required protective material '{code}' is not in the catalogue.")
        elif not m.is_active:
            blockers.append(f"Required protective material {m.name} is inactive.")

    evaluations: dict[int, dict] = {}
    to_pack: list[dict] = []
    for c in cartons:
        if only_carton_id is not None and c.id != only_carton_id and not c.is_baseline:
            continue
        snap = carton_snapshot(c)
        ev = {"carton": snap, "checks": [], "reasons": [], "warnings": [], "placement": None, "materials": [],
              "cost": None, "status": "rejected"}
        evaluations[c.id] = ev
        if not c.is_active:
            ev["checks"].append({"name": "active", "ok": False, "detail": "Carton is inactive"})
            ev["reasons"].append("Carton is inactive.")
            if not c.is_baseline:
                ev["status"] = "inactive"
                continue
        else:
            ev["checks"].append({"name": "active", "ok": True, "detail": "Active"})

        dim_problems = dimension_precheck(units, snap)
        ev["checks"].append({"name": "dimensions", "ok": not dim_problems,
                             "detail": "Every padded item fits the floor and height" if not dim_problems
                             else f"{len(dim_problems)} item(s) too large"})
        ev["reasons"] += dim_problems

        if c.max_weight_g is None:
            ev["checks"].append({"name": "weight", "ok": True, "not_checked": True,
                                 "detail": f"{total_weight} g; no weight limit configured for this carton"})
            ev["warnings"].append(f"No maximum weight is configured for {c.name}, so the {total_weight / 1000:.2f} kg "
                                  "order weight was not checked against a limit.")
        else:
            weight_ok = total_weight <= c.max_weight_g
            ev["checks"].append({"name": "weight", "ok": weight_ok,
                                 "detail": f"{total_weight} g of {c.max_weight_g} g limit"})
            if not weight_ok:
                ev["reasons"].append(f"Order weighs {total_weight / 1000:.2f} kg; carton limit is {c.max_weight_g / 1000:.2f} kg.")
        if not c.internal_verified:
            ev["warnings"].append(f"{c.name}: internal dimensions not verified; the nominal size "
                                  f"{' × '.join(str(x) for x in [c.nominal_length_mm, c.nominal_width_mm, c.nominal_height_mm])} mm "
                                  "is used for fitting.")

        if not dim_problems:
            to_pack.append({"id": f"C{c.id}", "l": snap["dims_mm"][0], "w": snap["dims_mm"][1], "h": snap["dims_mm"][2]})

    algorithm = settings.packing_algorithm
    if algorithm in ENGINE_CUSHION_TOTAL_MM:
        engine_items = [{"id": u["ref"], "l": u["engine_mm"][0], "w": u["engine_mm"][1], "h": u["engine_mm"][2],
                         "fragile": bool(u["fragile"])} for u in units]
    else:
        engine_items = [{"id": u["ref"], "l": u["padded_mm"][0], "w": u["padded_mm"][1],
                         "h": u["padded_mm"][2]} for u in units]
    engine_request = {"algorithm": algorithm, "items": engine_items, "cartons": to_pack}
    engine_response = None
    if to_pack and units:
        engine_response = packer_client.pack_cartons(engine_items, to_pack, algorithm)
        if engine_response.get("algorithm", "original") != algorithm:
            raise packer_client.PackerError(502, "algorithm_mismatch",
                                            f"Backend asked for the '{algorithm}' algorithm but the C++ service "
                                            f"answered with '{engine_response.get('algorithm', 'original')}'. "
                                            "Rebuild or update the C++ packing service.")
        for res in engine_response["results"]:
            ev = evaluations[int(res["carton_id"][1:])]
            ok = bool(res["fits"])
            ev["checks"].append({"name": "placement", "ok": ok,
                                 "detail": ("Engine found a layered placement" if algorithm == "optimizer"
                                            else "Engine found a single-layer placement") if ok
                                 else "Engine could not place every item"})
            if ok:
                chosen_try = next(a for a in res["attempts"] if a["orientation"] == res["orientation"])
                ev["placement"] = {"orientation": res["orientation"], "used_mm": res["used"],
                                   "placements": res["placements"], "attempts": res["attempts"],
                                   "search": {"widths_tried": sum(a.get("widths_tried", 0) for a in res["attempts"]),
                                              "widths_that_fit": sum(a.get("widths_that_fit", 0) for a in res["attempts"]),
                                              "best_width_mm": chosen_try.get("best_width")}}
            else:
                reasons = sorted({a.get("reason", "") for a in res["attempts"] if a.get("reason")})
                ev["reasons"].append("Packing engine: " + " / ".join(reasons))
                ev["engine_attempts"] = res["attempts"]

    # stock, materials, cost
    for cid, ev in evaluations.items():
        snap = ev["carton"]
        if ev["status"] == "inactive":
            continue
        geometric_ok = ev["placement"] is not None and all(
            ch["ok"] for ch in ev["checks"] if ch["name"] in ("dimensions", "weight", "placement"))
        ev["physically_feasible"] = geometric_ok and not blockers
        if blockers:
            ev["reasons"] += blockers
        mat_lines = material_plan(units, snap["volume_cm3"], materials)
        ev["materials"] = mat_lines
        ev["cost"] = price(snap["unit_cost"], mat_lines)
        ev["utilization"] = round(product_volume / snap["volume_cm3"], 4) if snap["volume_cm3"] else None
        ev["void_cm3"] = round(snap["volume_cm3"] - product_volume, 1)
        ev["padded_fill"] = round(min(1, padded_volume / snap["volume_cm3"]), 4) if snap["volume_cm3"] else None

        stock_ok = snap["available"] >= 1
        ev["checks"].append({"name": "carton_stock", "ok": stock_ok,
                             "detail": f"{snap['available']} available ({snap['stock']} in stock, {snap['reserved']} reserved)"})
        if not stock_ok:
            ev["reasons"].append(f"No {snap['name']} cartons available ({snap['stock']} in stock, {snap['reserved']} reserved).")

        mat_ok = True
        for ln in mat_lines:
            if not ln["exists"] or not ln["active"] or ln["available"] < ln["quantity"]:
                mat_ok = False
                ev["reasons"].append(f"Not enough {ln['name']}: need {ln['quantity']} {ln['unit']}, "
                                     f"{max(ln['available'], 0)} available.")
        ev["checks"].append({"name": "materials", "ok": mat_ok,
                             "detail": "Protective materials available" if mat_ok else "Material shortage"})

        if snap["is_active"] and ev["physically_feasible"] and stock_ok and mat_ok:
            ev["status"] = "feasible"

    for ev in evaluations.values():
        ev["short_reason"] = None if ev["status"] == "feasible" else (
            "switched off" if ev["status"] == "inactive" else _short_reason(ev))

    feasible = [ev for ev in evaluations.values() if ev["status"] == "feasible"
                and (only_carton_id is None or ev["carton"]["id"] == only_carton_id)]
    # The smallest carton that holds everything wins: least volume means least air shipped,
    # least void fill and usually the lowest cost. Equal volumes go to the cheaper carton.
    feasible.sort(key=lambda ev: (ev["carton"]["volume_cm3"], ev["cost"]["total"] is None, ev["cost"]["total"] or 0))
    chosen = feasible[0] if feasible else None

    custom_ev, design_response = None, None
    if only_carton_id is None:
        custom_ev, design_response = _made_to_measure(mtm_carton, chosen, units, blockers, materials,
                                                      engine_items, product_volume, padded_volume, total_weight)
        if custom_ev:
            evaluations[mtm_carton.id] = custom_ev
            chosen = custom_ev

    baseline_info = _baseline(evaluations, baseline, chosen)

    if chosen and chosen is not custom_ev:
        c = chosen["carton"]
        smaller = [ev for ev in evaluations.values() if ev is not chosen and ev["status"] not in ("feasible", "inactive")
                   and ev["carton"]["volume_cm3"] <= c["volume_cm3"]]
        why = [f"Smallest of the {len([e for e in evaluations.values() if e['status'] != 'inactive'])} warehouse "
               f"cartons that holds the whole order: {c['name']} "
               f"({' × '.join(fmt(x) for x in c['dims_cm'])} cm), "
               f"{round((chosen['padded_fill'] or 0) * 100)}% of its volume is product and padding"]
        if smaller:
            why.append("Smaller cartons were ruled out: " + "; ".join(
                f"{ev['carton']['name']} ({_short_reason(ev)})" for ev in sorted(smaller, key=lambda e: e["carton"]["volume_cm3"])))
        larger = [ev for ev in feasible if ev is not chosen]
        if larger:
            nxt = larger[0]
            why.append(f"Next size that also fits: {nxt['carton']['name']}, "
                       f"{round(nxt['carton']['volume_cm3'] / c['volume_cm3'], 1)}× the volume")
        search = (chosen.get("placement") or {}).get("search")
        if search:
            why.append(f"Layout: the packing algorithm tried {search['widths_tried']} row widths in this carton "
                       f"(both ways round), {search['widths_that_fit']} of them fit, and the tightest layout was kept")
        chosen["why"] = why

    alternatives = [] if chosen else _alternatives(evaluations, units, blockers, total_weight)

    return {
        "units": units,
        "blockers": blockers,
        "alternatives": alternatives,
        "warnings": (chosen or {}).get("warnings", []),
        "totals": {"unit_count": len(units), "weight_g": total_weight,
                   "product_volume_cm3": round(product_volume, 1),
                   "fragile_units": sum(1 for u in units if u["fragile"])},
        "rules": {"fragile_min_padding_cm": settings.fragile_min_padding_cm,
                  "void_fill_material_code": settings.void_fill_material_code,
                  "void_fill_cm3_per_unit": settings.void_fill_cm3_per_unit,
                  "rounding": "product dimensions rounded up, carton dimensions rounded down to whole mm",
                  "algorithm": algorithm,
                  "engine_limits": ("optimizer: rows, then layers stacked up to the carton height (max 300 mm); "
                                    "fragile items get a 15 mm cushion on every side; "
                                    "items stay upright, 90° floor rotation only")
                  if algorithm == "optimizer" else
                  ("optimizer2: single layer, no stacking; fragile items get a 7.5 mm cushion on every side; "
                   "items stay upright, 90° floor rotation only")
                  if algorithm == "optimizer2" else
                  "single layer, no stacking, items stay upright, 90° floor rotation only"},
        "evaluations": sorted(evaluations.values(), key=lambda ev: ev["carton"]["volume_cm3"]),
        "chosen_carton_id": chosen["carton"]["id"] if chosen else None,
        "baseline": baseline_info,
        "made_to_measure": ({"box_mm": [design_response["box"]["W"], design_response["box"]["L"],
                                         design_response["box"]["H"]],
                             "used": custom_ev is not None,
                             "rule": f"used when no stock carton fits or the smallest one is over "
                                     f"{settings.custom_box_when_stock_over:g}x this volume"}
                            if design_response else None),
        "engine": {"request": engine_request,
                   "response_meta": {k: v for k, v in (engine_response or {}).items() if k != "results"},
                   # the C++ service's JSON results, unedited (one entry per carton sent to it)
                   "response_results": (engine_response or {}).get("results", [])},
    }


def _made_to_measure(mtm: Optional[Carton], stock: Optional[dict], units: list[dict], blockers: list[str],
                     materials: dict, engine_items: list[dict], product_volume: float, padded_volume: float,
                     total_weight: int):
    """EDGE CASES ONLY: a box cut to optimizer2's own design. Returns (evaluation or None, design response)."""
    ratio = settings.custom_box_when_stock_over
    if (settings.packing_algorithm != "optimizer2" or ratio <= 0 or not units or blockers
            or mtm is None or not mtm.is_active):
        return None, None
    try:
        d = packer_client.design(engine_items, "optimizer2")
    except packer_client.PackerError:
        return None, None
    if d.get("algorithm") != "optimizer2":
        return None, None
    W, L, H = d["box"]["W"], d["box"]["L"], d["box"]["H"]
    volume_cm3 = round(W * L * H / 1000, 1)
    if stock is not None and stock["carton"]["volume_cm3"] <= ratio * volume_cm3:
        return None, d                                   # the stock carton is close enough: no need
    dims_cm = [W / 10, L / 10, H / 10]
    snap = carton_snapshot(mtm)
    board = custom_box_cost(dims_cm)
    snap.update({"name": "Made-to-measure box", "dims_cm": dims_cm, "dims_mm": [W, L, H], "nominal_mm": [W, L, H],
                 "volume_cm3": volume_cm3, "unit_cost": board["unit_cost"], "internal_verified": False,
                 "sample_fields": sorted(set(snap["sample_fields"]) | {"unit_cost"}), "is_baseline": False})
    mat_lines = material_plan(units, volume_cm3, materials)
    stock_ok = snap["available"] >= 1
    mat_ok = all(ln["exists"] and ln["active"] and ln["available"] >= ln["quantity"] for ln in mat_lines)
    if not (stock_ok and mat_ok):
        return None, d
    why = ([f"No stock carton holds this order, so a box is cut to the algorithm's design: "
            f"{' × '.join(str(x) for x in [W, L, H])} mm"] if stock is None else
           [f"Made-to-measure box {' × '.join(str(x) for x in [W, L, H])} mm ({volume_cm3 / 1000:.2f} L): the smallest "
            f"stock carton that fits, {stock['carton']['name']} ({stock['carton']['volume_cm3'] / 1000:.1f} L), is "
            f"{stock['carton']['volume_cm3'] / volume_cm3:.1f}x that volume"])
    why.append(f"Board cost estimate: {board['rule']}")
    ev = {"carton": snap, "reasons": [], "status": "feasible", "physically_feasible": True,
          "checks": [{"name": "active", "ok": True, "detail": "Made-to-measure boxes enabled"},
                     {"name": "dimensions", "ok": True, "detail": "Box is cut to the algorithm's layout"},
                     {"name": "weight", "ok": True, "not_checked": True,
                      "detail": f"{total_weight} g; no weight limit configured for made-to-measure boxes"},
                     {"name": "placement", "ok": True, "detail": "Engine designed the box around a single layer"},
                     {"name": "carton_stock", "ok": True, "detail": f"{snap['available']} board blanks available"},
                     {"name": "materials", "ok": True, "detail": "Protective materials available"}],
          "warnings": ["Made-to-measure box: the size comes from the packing algorithm and the board cost is an "
                       "estimate (sample price)."],
          "placement": {"orientation": "rows_along_length", "used_mm": {"x": W, "y": L, "z": H},
                        "placements": d["placements"], "attempts": [], "search": None},
          "materials": mat_lines, "cost": price(board["unit_cost"], mat_lines),
          "utilization": round(product_volume / volume_cm3, 4) if volume_cm3 else None,
          "void_cm3": round(volume_cm3 - product_volume, 1),
          "padded_fill": round(min(1, padded_volume / volume_cm3), 4) if volume_cm3 else None,
          "short_reason": None, "why": why, "made_to_measure": True}
    return ev, d


def _alternatives(evaluations: dict, units: list[dict], blockers: list[str], total_weight: int) -> list[dict]:
    """When no carton fits: what could be done instead. Every suggestion is derived from the
    checks above; nothing here claims the engine has packed anything."""
    out = []
    active = [ev for ev in evaluations.values() if ev["status"] != "inactive"]
    if blockers:
        out.append({"kind": "fix_product_data", "text": "Fix the product packaging data first: " + " ".join(blockers)})
    if not active:
        out.append({"kind": "activate_carton", "text": "No carton is active. Activate a carton on the Cartons page."})
        return out
    tallest = max(ev["carton"]["dims_mm"][2] for ev in active)

    def fits_some_floor(u):
        a, b = u["padded_mm"][:2]
        return any((a <= L and b <= W) or (b <= L and a <= W) for L, W, _ in (ev["carton"]["dims_mm"] for ev in active))
    too_tall = [u for u in units if u["padded_mm"][2] > tallest]
    for u in {u["product_id"]: u for u in too_tall}.values():
        out.append({"kind": "taller_carton",
                    "text": f"{u['name']} needs {u['padded_mm'][2]} mm of internal height with padding; the tallest "
                            f"active carton has {tallest} mm. Add a carton at least {u['padded_mm'][2]} mm tall "
                            "(items are never tipped over)."})
    too_wide = [u for u in units if u not in too_tall and not fits_some_floor(u)]
    for u in {u["product_id"]: u for u in too_wide}.values():
        out.append({"kind": "larger_floor",
                    "text": f"{u['name']} needs a floor of at least {u['padded_mm'][0]} × {u['padded_mm'][1]} mm "
                            "(either way round); no active carton has one. Add a larger carton."})
    weight_limits = [ev["carton"]["max_weight_g"] for ev in active if ev["carton"]["max_weight_g"] is not None]
    if weight_limits and len(weight_limits) == len(active) and total_weight > max(weight_limits):
        out.append({"kind": "weight", "text": f"The order weighs {total_weight / 1000:.2f} kg, above every carton's "
                                              f"limit (highest {max(weight_limits) / 1000:.2f} kg). Split it into parcels."})
    restock = [ev for ev in active if ev.get("physically_feasible") and
               not next((ch["ok"] for ch in ev["checks"] if ch["name"] == "carton_stock"), True)]
    for ev in restock:
        out.append({"kind": "restock_carton", "carton_id": ev["carton"]["id"],
                    "text": f"{ev['carton']['name']} would hold this order but has no free stock. Restock it."})
    mats = [ev for ev in active if ev.get("physically_feasible") and
            not next((ch["ok"] for ch in ev["checks"] if ch["name"] == "materials"), True)]
    if mats and not restock:
        out.append({"kind": "restock_material", "text": "A carton fits but a protective material is short: "
                                                        + mats[0]["reasons"][-1]})
    if not too_tall and not too_wide and not restock and not mats and len(units) > 1:
        engine = "packing engine" if optimizer_on() else "single-layer engine"
        out.append({"kind": "split", "text": f"Every item fits some carton on its own, but the {engine} "
                                             "cannot place all of them in one carton. Split the order into two or "
                                             "more parcels, or add a larger carton."})
    return out


def _short_reason(ev: dict) -> str:
    names = {ch["name"] for ch in ev["checks"] if not ch["ok"]}
    if "dimensions" in names:
        r = " ".join(ev["reasons"]).lower()
        return "an item is too tall" if "taller" in r else "an item is too wide"
    if "placement" in names:
        return "items do not all fit, even stacked" if optimizer_on() else "items do not all fit on the floor"
    if "weight" in names:
        return "too heavy"
    if "carton_stock" in names:
        return "out of stock"
    if "materials" in names:
        return "material shortage"
    return ev["reasons"][0] if ev["reasons"] else "not suitable"


def _baseline(evaluations: dict, baseline: Optional[Carton], chosen: Optional[dict]) -> dict:
    if baseline is None:
        return {"available": False, "reason": "No baseline carton is designated in the carton catalogue."}
    ev = evaluations.get(baseline.id)
    info = {"carton": carton_snapshot(baseline), "available": False}
    if not ev or not ev.get("physically_feasible"):
        info["reason"] = "The baseline carton cannot safely hold this order, so no comparison is made."
        return info
    if ev["cost"]["total"] is None:
        info["reason"] = "Baseline cost data is missing: " + ", ".join(ev["cost"]["missing"])
        return info
    info.update({"available": True, "cost": ev["cost"], "volume_cm3": ev["carton"]["volume_cm3"],
                 "materials": ev["materials"]})
    if chosen and chosen["cost"]["total"] is not None:
        info["savings"] = round(ev["cost"]["total"] - chosen["cost"]["total"], 2)
        info["volume_reduction_cm3"] = round(ev["carton"]["volume_cm3"] - chosen["carton"]["volume_cm3"], 1)
    return info
