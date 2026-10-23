"""Pydantic request schemas (server-side validation)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def email_ok(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Enter a valid email address")
        return v


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class WorkerLoginIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    worker_name: str = Field(min_length=2, max_length=60)


class CartQtyIn(BaseModel):
    quantity: int = Field(ge=0, le=99)


class CartMergeIn(BaseModel):
    items: list[dict] = Field(default_factory=list, max_length=100)


class Contact(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    phone: str = Field(min_length=7, max_length=20)


class Address(BaseModel):
    line1: str = Field(min_length=3, max_length=200)
    line2: str = Field(default="", max_length=200)
    city: str = Field(min_length=2, max_length=80)
    state: str = Field(min_length=2, max_length=80)
    postal_code: str = Field(min_length=4, max_length=12)
    country: str = Field(default="India", max_length=60)


class Payment(BaseModel):
    method: Literal["card", "upi", "cod"] = "card"
    confirm_simulated: bool

    @field_validator("confirm_simulated")
    @classmethod
    def must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Confirm that this is a simulated payment")
        return v


class CheckoutIn(BaseModel):
    contact: Contact
    address: Address
    payment: Payment


class AdminCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=200)


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    brand: str = Field(default="TOTE", max_length=80)
    description: str = Field(default="", max_length=4000)
    category: str = Field(min_length=2, max_length=60)
    price: float = Field(gt=0, le=1_000_000)
    image_url: Optional[str] = Field(default=None, max_length=500)
    stock: int = Field(ge=0, le=1_000_000)
    featured: bool = False
    is_active: bool = True
    length_cm: float = Field(gt=0, le=500)
    width_cm: float = Field(gt=0, le=500)
    height_cm: float = Field(gt=0, le=500)
    weight_g: int = Field(gt=0, le=100_000)
    fragile: bool = False
    padding_cm: float = Field(default=0, ge=0, le=20)
    orientation: Literal["upright", "any"] = "any"
    protection_material_code: Optional[str] = Field(default=None, max_length=40)
    protection_qty_per_unit: int = Field(default=0, ge=0, le=50)
    handling_instructions: str = Field(default="", max_length=1000)
    restrictions: str = Field(default="", max_length=1000)


class ProductPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    brand: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = Field(default=None, max_length=4000)
    category: Optional[str] = Field(default=None, min_length=2, max_length=60)
    price: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    image_url: Optional[str] = Field(default=None, max_length=500)
    stock: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    featured: Optional[bool] = None
    is_active: Optional[bool] = None
    length_cm: Optional[float] = Field(default=None, gt=0, le=500)
    width_cm: Optional[float] = Field(default=None, gt=0, le=500)
    height_cm: Optional[float] = Field(default=None, gt=0, le=500)
    weight_g: Optional[int] = Field(default=None, gt=0, le=100_000)
    fragile: Optional[bool] = None
    padding_cm: Optional[float] = Field(default=None, ge=0, le=20)
    orientation: Optional[Literal["upright", "any"]] = None
    protection_material_code: Optional[str] = Field(default=None, max_length=40)
    protection_qty_per_unit: Optional[int] = Field(default=None, ge=0, le=50)
    handling_instructions: Optional[str] = Field(default=None, max_length=1000)
    restrictions: Optional[str] = Field(default=None, max_length=1000)


def MM():                                  # whole millimetres, 1 mm .. 3 m
    return Field(gt=0, le=3000)


def OPT_MM():
    return Field(default=None, gt=0, le=3000)


class CartonIn(BaseModel):
    """Admin-created carton. Sizes in whole millimetres. Internal size defaults to the nominal size."""
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=80)
    category: str = Field(default="Custom", min_length=2, max_length=80)
    nominal_length_mm: int = MM()
    nominal_width_mm: int = MM()
    nominal_height_mm: int = MM()
    length_mm: Optional[int] = OPT_MM()
    width_mm: Optional[int] = OPT_MM()
    height_mm: Optional[int] = OPT_MM()
    internal_verified: bool = False
    max_weight_g: Optional[int] = Field(default=None, gt=0, le=100_000)
    unit_cost: Optional[float] = Field(default=None, ge=0, le=100_000)
    stock: int = Field(default=0, ge=0, le=1_000_000)
    min_stock: int = Field(default=0, ge=0, le=1_000_000)
    is_active: bool = True
    is_baseline: bool = False
    notes: str = Field(default="", max_length=1000)


class CartonPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    category: Optional[str] = Field(default=None, min_length=2, max_length=80)
    nominal_length_mm: Optional[int] = OPT_MM()
    nominal_width_mm: Optional[int] = OPT_MM()
    nominal_height_mm: Optional[int] = OPT_MM()
    length_mm: Optional[int] = OPT_MM()
    width_mm: Optional[int] = OPT_MM()
    height_mm: Optional[int] = OPT_MM()
    internal_verified: Optional[bool] = None
    max_weight_g: Optional[int] = Field(default=None, gt=0, le=100_000)
    clear_max_weight: bool = False
    unit_cost: Optional[float] = Field(default=None, ge=0, le=100_000)
    clear_unit_cost: bool = False
    min_stock: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    is_active: Optional[bool] = None
    is_baseline: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


class MaterialIn(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=80)
    unit: str = Field(min_length=1, max_length=20)
    stock: int = Field(default=0, ge=0, le=10_000_000)
    min_stock: int = Field(default=0, ge=0, le=10_000_000)
    unit_cost: Optional[float] = Field(default=None, ge=0, le=100_000)
    is_active: bool = True
    notes: str = Field(default="", max_length=1000)


class MaterialPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=20)
    min_stock: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    unit_cost: Optional[float] = Field(default=None, ge=0, le=100_000)
    clear_unit_cost: bool = False
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


class StockAdjustIn(BaseModel):
    delta: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=3, max_length=300)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class OverrideIn(BaseModel):
    carton_id: int
    reason: str = Field(min_length=10, max_length=500)


class MaterialUse(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    quantity: int = Field(ge=0, le=10_000)


class CompleteIn(BaseModel):
    materials_used: list[MaterialUse] = Field(default_factory=list)
    checklist: dict[str, bool]
    notes: str = Field(default="", max_length=1000)


class DispatchIn(BaseModel):
    status: Literal["ready_for_dispatch", "dispatched"]


class PriorityIn(BaseModel):
    priority: bool
    reason: str = Field(min_length=3, max_length=300)
