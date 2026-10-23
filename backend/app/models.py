"""Database tables. Units: cartons in millimetres; products in centimetres; grams; Indian rupees (INR)."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- users & auth
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="customer")  # customer | admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20))  # customer | worker | admin
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    worker_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user: Mapped[Optional[User]] = relationship()


# ---------------------------------------------------------------- catalogue
class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    brand: Mapped[str] = mapped_column(String(80), default="TOTE")
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(60), index=True)
    price: Mapped[float] = mapped_column(Float)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    art: Mapped[dict] = mapped_column(JSON, default=dict)  # illustration spec for the storefront
    stock: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Packaging metadata (simplified bounding boxes, see README)
    length_cm: Mapped[float] = mapped_column(Float)
    width_cm: Mapped[float] = mapped_column(Float)
    height_cm: Mapped[float] = mapped_column(Float)
    weight_g: Mapped[int] = mapped_column(Integer)
    fragile: Mapped[bool] = mapped_column(Boolean, default=False)
    padding_cm: Mapped[float] = mapped_column(Float, default=0)
    orientation: Mapped[str] = mapped_column(String(20), default="any")  # upright | any
    protection_material_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    protection_qty_per_unit: Mapped[int] = mapped_column(Integer, default=0)
    handling_instructions: Mapped[str] = mapped_column(Text, default="")
    restrictions: Mapped[str] = mapped_column(Text, default="")

    reviews: Mapped[list["Review"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    author: Mapped[str] = mapped_column(String(80))
    rating: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120), default="")
    body: Mapped[str] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    product: Mapped[Product] = relationship(back_populates="reviews")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    product: Mapped[Product] = relationship()


class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    product: Mapped[Product] = relationship()


class RecentlyViewed(Base):
    __tablename__ = "recently_viewed"
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    viewed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    product: Mapped[Product] = relationship()


# ---------------------------------------------------------------- orders
ORDER_STATUSES = ["placed", "awaiting_packing", "packing_in_progress", "packed",
                  "ready_for_dispatch", "dispatched"]


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True, default="placed")
    priority: Mapped[bool] = mapped_column(Boolean, default=False)
    priority_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact: Mapped[dict] = mapped_column(JSON)
    address: Mapped[dict] = mapped_column(JSON)
    subtotal: Mapped[float] = mapped_column(Float)
    shipping: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    payment_ref: Mapped[str] = mapped_column(String(40))
    # Client-generated key for one checkout attempt; a repeated submit returns the same order.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order", order_by="OrderEvent.id",
                                                      cascade="all, delete-orphan")
    user: Mapped[User] = relationship()


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(160))      # snapshot at purchase
    unit_price: Mapped[float] = mapped_column(Float)    # snapshot at purchase
    quantity: Mapped[int] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(120), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    order: Mapped[Order] = relationship(back_populates="events")


# ---------------------------------------------------------------- inventory
class Carton(Base):
    """A carton size. Dimensions are stored in whole millimetres (the canonical unit).

    nominal_*_mm  the size the carton is sold/labelled as (e.g. "300 x 230 x 100 mm").
    *_mm          the INTERNAL usable size. Every fit calculation uses these. Until someone
                  measures a real carton and ticks internal_verified, they default to the
                  nominal size and the UI says so.
    """
    __tablename__ = "cartons"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(80), default="Custom")
    nominal_length_mm: Mapped[int] = mapped_column(Integer)
    nominal_width_mm: Mapped[int] = mapped_column(Integer)
    nominal_height_mm: Mapped[int] = mapped_column(Integer)
    length_mm: Mapped[int] = mapped_column(Integer)   # internal usable dimensions
    width_mm: Mapped[int] = mapped_column(Integer)
    height_mm: Mapped[int] = mapped_column(Integer)
    internal_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    max_weight_g: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = not configured
    unit_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    min_stock: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    is_predefined: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fields that still hold seeded SAMPLE values (e.g. ["unit_cost", "stock"]). A field is
    # removed from this list as soon as an admin enters a real value for it.
    sample_fields: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    # Centimetre views of the internal size, for code that works in cm.
    @property
    def length_cm(self) -> float:
        return self.length_mm / 10

    @property
    def width_cm(self) -> float:
        return self.width_mm / 10

    @property
    def height_cm(self) -> float:
        return self.height_mm / 10

    @property
    def volume_mm3(self) -> int:
        return self.length_mm * self.width_mm * self.height_mm


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    unit: Mapped[str] = mapped_column(String(20))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    min_stock: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------- packing
PLAN_STATUSES = ["recommended", "accepted", "completed", "cancelled", "superseded", "no_fit"]


class PackingPlan(Base):
    __tablename__ = "packing_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    carton_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cartons.id"), nullable=True)
    recommended_carton_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cartons.id"), nullable=True)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_plan_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packing_plans.id"), nullable=True)
    # Frozen copies of everything used to build the plan (costs, dimensions, algorithm I/O).
    snapshot: Mapped[dict] = mapped_column(JSON)
    estimated_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    baseline_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_savings: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    void_cm3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carton_volume_cm3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    baseline_volume_cm3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    order: Mapped[Order] = relationship()
    carton: Mapped[Optional[Carton]] = relationship(foreign_keys=[carton_id])
    placements: Mapped[list["PlacementRecord"]] = relationship(order_by="PlacementRecord.seq",
                                                               cascade="all, delete-orphan")
    reservations: Mapped[list["Reservation"]] = relationship(cascade="all, delete-orphan")


class PlacementRecord(Base):
    __tablename__ = "placements"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("packing_plans.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    unit_ref: Mapped[str] = mapped_column(String(40))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(160))
    # Padded slot reserved by the algorithm (cm, carton frame)
    x_cm: Mapped[float] = mapped_column(Float)
    y_cm: Mapped[float] = mapped_column(Float)
    z_cm: Mapped[float] = mapped_column(Float)
    dx_cm: Mapped[float] = mapped_column(Float)
    dy_cm: Mapped[float] = mapped_column(Float)
    dz_cm: Mapped[float] = mapped_column(Float)
    padding_cm: Mapped[float] = mapped_column(Float)
    rotated: Mapped[bool] = mapped_column(Boolean)


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("packing_plans.id"), index=True)
    item_type: Mapped[str] = mapped_column(String(10))  # carton | material
    item_id: Mapped[int] = mapped_column(Integer)
    item_code: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="active", index=True)  # active|released|consumed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_movement_item", "item_type", "item_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    item_type: Mapped[str] = mapped_column(String(10))
    item_id: Mapped[int] = mapped_column(Integer)
    item_code: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20))  # initial|adjust|reserve|release|consume
    stock_delta: Mapped[int] = mapped_column(Integer, default=0)
    reserved_delta: Mapped[int] = mapped_column(Integer, default=0)
    stock_after: Mapped[int] = mapped_column(Integer)
    reserved_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")
    plan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actor: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PackingCompletion(Base):
    __tablename__ = "packing_completions"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("packing_plans.id"), unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    carton_id: Mapped[int] = mapped_column(ForeignKey("cartons.id"))
    carton_code: Mapped[str] = mapped_column(String(40))
    materials_used: Mapped[list] = mapped_column(JSON)  # [{code, qty, unit_cost}]
    actual_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    baseline_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_savings: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    checklist: Mapped[dict] = mapped_column(JSON)
    notes: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class WorkerOverride(Base):
    __tablename__ = "worker_overrides"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    original_plan_id: Mapped[int] = mapped_column(ForeignKey("packing_plans.id"))
    new_plan_id: Mapped[int] = mapped_column(ForeignKey("packing_plans.id"))
    original_carton_code: Mapped[str] = mapped_column(String(40))
    selected_carton_code: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(120))
    original_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    original_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(30), index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
