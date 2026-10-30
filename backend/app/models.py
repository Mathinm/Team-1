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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

QTY = Numeric(12, 3)
MONEY = Numeric(12, 2)


def _now_col():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


# Products and batches
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
    unit: Mapped[str] = mapped_column(String(10))
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
    quantity: Mapped[Decimal] = mapped_column(QTY)
    initial_quantity: Mapped[Decimal] = mapped_column(QTY)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expiry_date: Mapped[date] = mapped_column(Date)


# Sales
class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        UniqueConstraint("device_id", "event_id", name="uq_sales_device_event"),
    )

    sale_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    sku: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(10))
    unit_price: Mapped[Decimal] = mapped_column(MONEY)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = _now_col()
    source: Mapped[str] = mapped_column(String(10))
    recorded_by: Mapped[str] = mapped_column(String(80))
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.device_id"), nullable=True
    )
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SaleBatch(Base):
    """Which batches a sale was taken from (FEFO trail)."""

    __tablename__ = "sale_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.sale_id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.batch_id"))
    quantity: Mapped[Decimal] = mapped_column(QTY)


# Devices
class Device(Base):
    """A POS or sensor source with its own key. Only the SHA-256 of the key is stored."""

    __tablename__ = "devices"

    device_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(10))
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
    unit_id: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(12))
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(10), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = _now_col()


# Users and login
ROLES = ("Admin", "Manager", "Inventory Staff", "Cashier")


class User(Base):
    """A person who logs in. Never deleted, only deactivated."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('Admin', 'Manager', 'Inventory Staff', 'Cashier')",
            name="ck_users_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    user_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _now_col()


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    sid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_pk: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = _now_col()
    last_seen_at: Mapped[datetime] = _now_col()
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# Stock counts and non-expiry removals
class StockCount(Base):
    __tablename__ = "stock_counts"

    stock_count_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.batch_id"), index=True)
    system_quantity: Mapped[Decimal] = mapped_column(QTY)
    counted_quantity: Mapped[Decimal] = mapped_column(QTY)
    variance: Mapped[Decimal] = mapped_column(QTY)
    reason: Mapped[str] = mapped_column(String(255))
    recorded_by: Mapped[str] = mapped_column(String(80))
    recorded_at: Mapped[datetime] = _now_col()


class Removal(Base):
    __tablename__ = "removals"

    removal_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.batch_id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    reason: Mapped[str] = mapped_column(String(40))
    recorded_by: Mapped[str] = mapped_column(String(80))
    recorded_at: Mapped[datetime] = _now_col()


# Notifications (Sprint 2, Issue #11)
class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "uq_notifications_expiry_batch_type",
            "store_id",
            "batch_id",
            "notification_type",
            unique=True,
            sqlite_where=text(
                "notification_type IN ('pre_expiry', 'expiry')"
            ),
            postgresql_where=text(
                "notification_type IN ('pre_expiry', 'expiry')"
            ),
        ),
    )

    notification_id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, default=1)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.batch_id"), index=True
    )
    removal_id: Mapped[int | None] = mapped_column(
        ForeignKey("removals.removal_id"), nullable=True
    )
    notification_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = _now_col()