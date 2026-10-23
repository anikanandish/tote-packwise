from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Carton, Product
from ..services import feasibility, packer_client

router = APIRouter(tags=["Health"])


@router.get("/api/health", summary="FastAPI + database health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "service": "tote-packwise-api", "database": "ok"}


@router.get("/api/health/packer", summary="C++ packing service health (checked over HTTP)")
def packer_health():
    try:
        return {"status": "ok", "packer_url": settings.packer_url, "engine": packer_client.health()}
    except packer_client.PackerUnavailable as e:
        raise HTTPException(503, str(e))


PREVIEW_SLUGS = [("rose-oud-eau-de-parfum", 1), ("gentle-nail-polish-remover", 1),
                 ("precision-liquid-eyeliner", 2), ("velvet-matte-lipstick", 1)]


@router.get("/api/public/engine-preview", tags=["Public"],
            summary="Live engine output for the PackWise landing page (demo products, smallest fitting carton)")
def engine_preview(db: Session = Depends(get_db)):
    lines = []
    for slug, qty in PREVIEW_SLUGS:
        p = db.query(Product).filter(Product.slug == slug).first()
        if p:
            lines.append(SimpleNamespace(product=p, quantity=qty))
    if not lines:
        raise HTTPException(404, "Demo products are not seeded.")
    units, _ = feasibility.build_units(SimpleNamespace(items=lines))
    from ..config import settings
    meta = {u["ref"]: u for u in units}
    try:
        cartons = [c for c in db.query(Carton).filter(Carton.is_active.is_(True)).all() if c.code != settings.custom_box_code]
        cartons.sort(key=lambda c: c.volume_mm3)
        resp = packer_client.pack_cartons(
            [{"id": u["ref"], "l": u["padded_mm"][0], "w": u["padded_mm"][1], "h": u["padded_mm"][2]} for u in units],
            [{"id": f"C{c.id}", "l": c.length_mm, "w": c.width_mm, "h": c.height_mm} for c in cartons])
    except (packer_client.PackerUnavailable, packer_client.PackerError) as e:
        raise HTTPException(503, f"Packing engine unavailable: {e}")
    by_id = {f"C{c.id}": c for c in cartons}
    fit = next((r for r in resp["results"] if r["fits"]), None)
    if not fit:
        return {"fits": False, "message": "No active carton fits the demo products."}
    c = by_id[fit["carton_id"]]
    return {"fits": True, "carton": {"name": c.name, "dims_cm": [c.length_cm, c.width_cm, c.height_cm]},
            "placements": [{**pl, "name": meta[pl["id"]]["name"], "fragile": meta[pl["id"]]["fragile"],
                            "padding_cm": meta[pl["id"]]["padding_cm"]} for pl in fit["placements"]],
            "rejected": [{"carton": by_id[r["carton_id"]].name, "reasons": [a.get("reason") for a in r["attempts"]]}
                         for r in resp["results"] if not r["fits"]],
            "engine": resp["engine"]}
