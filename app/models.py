from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_stores_name_nonempty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    products: Mapped[list["Product"]] = relationship(back_populates="store")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("shelf_life_days > 0", name="ck_products_shelf_life_positive"),
        CheckConstraint("cost_price >= 0", name="ck_products_cost_nonnegative"),
        CheckConstraint("selling_price > 0", name="ck_products_selling_positive"),
        CheckConstraint("low_stock_threshold >= 0", name="ck_products_threshold_nonnegative"),
        CheckConstraint("min_temperature < max_temperature", name="ck_products_temperature_range"),
        CheckConstraint("unit IN ('kg','piece','litre')", name="ck_products_unit"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    shelf_life_days: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_type: Mapped[str] = mapped_column(String(40), nullable=False)
    min_temperature: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    max_temperature: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    cost_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    selling_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10, server_default="10", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    store: Mapped["Store"] = relationship(back_populates="products")
