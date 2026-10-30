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

from app.crypto import EncryptedString
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