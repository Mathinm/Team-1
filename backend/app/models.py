"""Database tables.

Every store record carries store_id (NFR-14). Column names follow the frontend API contract.

Supplier and Product are the product master data from issue #5 (API in app/products/);
Batch is from issue #6 (API in app/batches/). The sales code in app/sales/fefo.py relies on
the attribute names sku, active, unit, selling_price, quantity, expiry_date and product_id.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

QTY = Numeric(12, 3)  # kg / l can be fractional; 3 decimals
MONEY = Numeric(12, 2)


def _now_col():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------- products (#5) and batches (#6)
class Supplier(Base):
    __tablename__ = "suppliers"
    supplier_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(120))


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("store_id", "sku"),)
    product_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    sku: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(10))  # kg | piece | l
    shelf_life_days: Mapped[int] = mapped_column(Integer)
    storage_type: Mapped[str] = mapped_column(String(20))
    temp_min: Mapped[float] = mapped_column(Float)
    temp_max: Mapped[float] = mapped_column(Float)
    cost_price: Mapped[Decimal] = mapped_column(MONEY)
    selling_price: Mapped[Decimal] = mapped_column(MONEY)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_batches_quantity_nonneg"),
        Index("ix_batches_product_expiry", "product_id", "expiry_date"),
    )
    batch_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.supplier_id"))
    quantity: Mapped[Decimal] = mapped_column(QTY)  # on hand now
    initial_quantity: Mapped[Decimal] = mapped_column(QTY)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expiry_date: Mapped[date] = mapped_column(Date)  # last day the batch may be sold


# ---------------------------------------------------------------- sales (S1-5)
class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        # A device resending an event (offline sync) must not create a second sale.
        UniqueConstraint("device_id", "event_id", name="uq_sales_device_event"),
    )
    sale_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    sku: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10))
    unit_price: Mapped[Decimal] = mapped_column(MONEY)  # price at the time of sale
    amount: Mapped[Decimal] = mapped_column(MONEY)
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = _now_col()
    source: Mapped[str] = mapped_column(String(10))  # manual | csv | device
    recorded_by: Mapped[str] = mapped_column(String(80))  # user id or "device:<name>" (audit)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.device_id"), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SaleBatch(Base):
    """Which batches a sale was taken from (FEFO trail)."""

    __tablename__ = "sale_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.sale_id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.batch_id"))
    quantity: Mapped[Decimal] = mapped_column(QTY)


# ---------------------------------------------------------------- device API (S1-2)
class Device(Base):
    """A POS or sensor source with its own key. Only the SHA-256 of the key is stored."""

    __tablename__ = "devices"
    device_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(10))  # pos | sensor
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _now_col()


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        UniqueConstraint("device_id", "event_id", name="uq_readings_device_event"),
        Index("ix_readings_unit_time", "store_id", "unit_id", "recorded_at"),
    )
    reading_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.device_id"))
    event_id: Mapped[str] = mapped_column(String(64))
    unit_id: Mapped[str] = mapped_column(String(64))  # e.g. "Fridge-1"
    type: Mapped[str] = mapped_column(String(12))  # temperature | door | power
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)  # temperature, deg C
    value_text: Mapped[str | None] = mapped_column(String(10), nullable=True)  # OPEN/CLOSED, ON/OFF
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # original time
    received_at: Mapped[datetime] = _now_col()


# ---------------------------------------------------------------- users and login (S1-1, #3)
ROLES = ("Admin", "Manager", "Inventory Staff", "Cashier")


class User(Base):
    """A person who logs in. Never deleted, only deactivated, so past records keep their author."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('Admin', 'Manager', 'Inventory Staff', 'Cashier')", name="ck_users_role"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    user_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # login name
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    # argon2id hash; the random per-user salt is stored inside it (NFR-9). Never the password.
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _now_col()
    # SEC-3: wrong passwords in a row, and when the account was locked (None = not locked)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserSession(Base):
    """One row per login. Logout or deactivation ends it, so its token stops working at once."""

    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    sid: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # the token's "sid"
    user_pk: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = _now_col()
    last_seen_at: Mapped[datetime] = _now_col()  # S2-9 idle logout compares against this
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
