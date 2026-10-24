"""HTTP client for the C++ packing microservice. The whole Python<->C++ interface lives here."""
import httpx

from ..config import settings


class PackerUnavailable(Exception):
    """The C++ service could not be reached."""


class PackerError(Exception):
    """The C++ service answered with an error."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _url(path: str) -> str:
    return settings.packer_url.rstrip("/") + path


def health() -> dict:
    try:
        r = httpx.get(_url("/health"), timeout=2.0)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise PackerUnavailable(f"Packing service at {settings.packer_url} is not reachable ({e.__class__.__name__}).")


def pack_cartons(items: list[dict], cartons: list[dict], algorithm: str | None = None) -> dict:
    """items: [{id, l, w, h[, fragile]}] and cartons: [{id, l, w, h}], integer millimetres.
    algorithm: None/"original" = original packer.cpp, "optimizer" = new optimizer.cpp."""
    body = {"items": items, "cartons": cartons}
    if algorithm:
        body["algorithm"] = algorithm
    try:
        r = httpx.post(_url("/v1/pack/cartons"), json=body,
                       timeout=settings.packer_timeout_s)
    except httpx.HTTPError as e:
        raise PackerUnavailable(f"Packing service at {settings.packer_url} is not reachable ({e.__class__.__name__}).")
    try:
        data = r.json()
    except ValueError:
        raise PackerError(r.status_code, "bad_response", "Packing service returned a non-JSON response.")
    if r.status_code != 200:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        raise PackerError(r.status_code, err.get("code", "error"), err.get("message", "Packing service error."))
    return data


def design(items: list[dict], algorithm: str | None = None) -> dict:
    """Design the smallest-scoring box for the items (mm). algorithm=None: original packer.cpp;
    "optimizer2": optimizer2.cpp's own design (fragile cushion added by the engine)."""
    body = {"items": items}
    if algorithm:
        body["algorithm"] = algorithm
    try:
        r = httpx.post(_url("/v1/pack/design"), json=body, timeout=settings.packer_timeout_s)
    except httpx.HTTPError as e:
        raise PackerUnavailable(f"Packing service at {settings.packer_url} is not reachable ({e.__class__.__name__}).")
    try:
        data = r.json()
    except ValueError:
        raise PackerError(r.status_code, "bad_response", "Packing service returned a non-JSON response.")
    if r.status_code != 200:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        raise PackerError(r.status_code, err.get("code", "error"), err.get("message", "Packing service error."))
    return data


def sweep(items: list[dict]) -> dict:
    """Original design() loop with every width trial recorded (for the simulator)."""
    try:
        r = httpx.post(_url("/v1/pack/sweep"), json={"items": items}, timeout=settings.packer_timeout_s)
    except httpx.HTTPError as e:
        raise PackerUnavailable(f"Packing service at {settings.packer_url} is not reachable ({e.__class__.__name__}).")
    try:
        data = r.json()
    except ValueError:
        raise PackerError(r.status_code, "bad_response", "Packing service returned a non-JSON response.")
    if r.status_code != 200:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        raise PackerError(r.status_code, err.get("code", "error"), err.get("message", "Packing service error."))
    return data
