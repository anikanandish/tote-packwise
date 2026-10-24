"""TOTE + PackWise API.

Run:  uvicorn app.main:app --reload --port 8000     (from the backend folder)
Docs: http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import database
from .config import settings
from .database import Base
from .routers import admin, auth, catalog, health, orders, packwise, sim_public, shop, simulator

log = logging.getLogger("tote")


def init_db():
    from . import migrate
    for step in migrate.run(database.engine):
        print(f"Database migration applied: {step}")
    Base.metadata.create_all(bind=database.engine)
    db = database.SessionLocal()
    try:
        from .seed import seed
        info = seed(db)
        if info.get("demo_order"):
            print(f"Seeded demo order {info['demo_order']}")
    finally:
        db.close()
    if not settings.worker_code:
        print("WARNING: PACKWISE_WORKER_CODE is not set - worker sign-in is disabled until you set it in backend/.env")
    if settings.admin_code_from_legacy:
        print("NOTE: ADMIN_ACCESS_CODE is not set, so the value of ADMIN_PASSWORD in backend/.env is the admin access code.")
    if not settings.admin_access_code:
        print("WARNING: ADMIN_ACCESS_CODE is not set - the admin console is locked until you set it in backend/.env")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="TOTE + PackWise API",
    version="1.0.0",
    description=(
        "Shared backend for the TOTE storefront and the PackWise warehouse app.\n\n"
        "**Auth:** call `/api/auth/login` (customer/admin) or `/api/auth/worker` (worker code), then click "
        "*Authorize* and paste the token.\n\n"
        "**Packing:** recommendations are computed by the separate C++ service over HTTP "
        f"(`{settings.packer_url}`). Algorithm in use: **{settings.packing_algorithm}** "
        "(set PACKING_ALGORITHM=optimizer or original in backend/.env). The optimizer packs rows, then "
        "stacked layers, and cushions fragile items; the original is single-layer. Neither tips items over; "
        "both only rotate items 90° on the floor."
    ),
    lifespan=lifespan,
)

# The simulator website (port 5175) is always allowed, even with an older .env that predates it.
SIM_SITE_ORIGINS = ["http://localhost:5175", "http://127.0.0.1:5175"]
app.add_middleware(CORSMiddleware, allow_origins=list(dict.fromkeys(settings.cors_origins + SIM_SITE_ORIGINS)), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"].replace("Value error, ", "")}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Please check the highlighted fields.", "errors": errors})


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server."})


for r in (health.router, auth.router, catalog.router, shop.router, orders.router, packwise.router, admin.router,
          simulator.router, sim_public.router):
    app.include_router(r)


@app.get("/", include_in_schema=False)
def root():
    return {"service": "TOTE + PackWise API", "docs": "/docs"}
