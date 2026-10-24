"""Application settings, read from environment variables (and backend/.env)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(BACKEND_DIR / 'data' / 'tote_packwise.db').as_posix()}")
    packer_url: str = os.getenv("PACKER_URL", "http://127.0.0.1:8090")
    packer_timeout_s: float = _float("PACKER_TIMEOUT_S", 5.0)

    # Shared code for warehouse workers. Never checked in the browser.
    worker_code: str = os.getenv("PACKWISE_WORKER_CODE", "")
    # Code that opens the admin console. Checked only on the server; never sent to the
    # browser, returned by the API or written to logs. Empty = admin console locked.
    # (An older .env without ADMIN_ACCESS_CODE keeps working: its ADMIN_PASSWORD value is used.)
    admin_access_code: str = os.getenv("ADMIN_ACCESS_CODE") or os.getenv("ADMIN_PASSWORD", "")
    admin_code_from_legacy: bool = not os.getenv("ADMIN_ACCESS_CODE") and bool(os.getenv("ADMIN_PASSWORD"))
    admin_login_max_failures: int = int(_float("ADMIN_LOGIN_MAX_FAILURES", 5))
    admin_login_lockout_s: float = _float("ADMIN_LOGIN_LOCKOUT_S", 300)
    # Seed the eight standard cartons with SAMPLE stock and SAMPLE prices (flagged as sample
    # in the UI) so the demo can pack straight away. false = stock 0 and no price.
    seed_sample_carton_values: bool = os.getenv("SEED_SAMPLE_CARTON_VALUES", "true").lower() == "true"

    session_hours: float = _float("SESSION_HOURS", 12)
    cors_origins: list = field(default_factory=lambda: [
        o.strip() for o in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,"
            "http://localhost:5175,http://127.0.0.1:5175"
        ).split(",") if o.strip()
    ])

    # Which packing algorithm chooses the carton for an order:
    #   optimizer -> the new optimizer (cpp-packer-service/original/optimizer.cpp): rows, layers,
    #                stacked layers, fixed 15 mm cushion on every side of fragile items
    #   original  -> the original packer.cpp: one layer, padding from the product data
    # To go back to the old algorithm set PACKING_ALGORITHM=original in backend/.env and restart.
    packing_algorithm: str = (os.getenv("PACKING_ALGORITHM", "optimizer").strip().lower()
                              if os.getenv("PACKING_ALGORITHM", "optimizer").strip().lower() in ("optimizer", "original")
                              else "optimizer")

    # Packing rules (documented in README "Packing rules").
    fragile_min_padding_cm: float = _float("FRAGILE_MIN_PADDING_CM", 1.0)
    void_fill_material_code: str = os.getenv("VOID_FILL_MATERIAL_CODE", "KRAFT")
    void_fill_cm3_per_unit: float = _float("VOID_FILL_CM3_PER_UNIT", 2000)

    # Earlier versions had a made-to-measure box (code below); it is no longer used for packing.
    # The board-cost figures remain for the simulator's "algorithm's ideal box" comparison.
    custom_box_code: str = os.getenv("CUSTOM_BOX_CODE", "CTN-CUSTOM")
    board_cost_per_m2: float = _float("BOARD_COST_PER_M2", 100)   # INR per m2 of corrugated board
    box_make_cost: float = _float("BOX_MAKE_COST", 2)               # INR per box (machine time, tape)

    shipping_flat: float = _float("SHIPPING_FLAT", 79)
    free_shipping_over: float = _float("FREE_SHIPPING_OVER", 1999)
    currency: str = os.getenv("CURRENCY", "INR")
    seed_demo_order: bool = os.getenv("SEED_DEMO_ORDER", "true").lower() == "true"


settings = Settings()
