"""DEV ONLY: load the frontend's demo shop, so the sales and device endpoints can be tried
before products/batches (#5, #6) are merged. Log in with POST /api/auth/login to get a token
(cashier1/cashier123 with SEED_DEMO_USERS=true, or the Admin from .env).

    docker compose exec backend python -m app.dev_seed

Safe to run twice (existing SKUs are skipped). Delete this file once #5/#6 are in.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import Batch, Product, Supplier
from app.sales.fefo import store_today
from app.stores import ensure_default_store

SUPPLIER = "Fresh Farms"

# sku, name, category, unit, cost, price, shelf-life days,
#   [(quantity, days since received, days until expiry), ...]
# Every batch keeps the shelf-life rule the receive form enforces (T6):
#   days since received + days until expiry <= shelf life.
DEMO = [
    ("TOM-01", "Tomato", "Vegetables", "kg", 18, 30, 7, [(12, 4, 2), (25, 2, 5)]),
    ("BAN-01", "Banana", "Fruits", "piece", 4, 6, 7, [(60, 2, 4)]),
    # first milk batch already expired, to show expiry alerts
    ("MLK-01", "Milk 1L", "Dairy", "l", 22, 28, 5, [(8, 6, -1), (30, 1, 3)]),
    ("PAN-01", "Paneer", "Dairy", "kg", 280, 360, 10, [(10, 3, 6)]),
    ("BRD-01", "Bread Loaf", "Bakery", "piece", 28, 40, 4, [(15, 1, 3), (7, 5, -1)]),
    ("SPN-01", "Spinach", "Vegetables", "kg", 30, 45, 3, [(10, 1, 2)]),
]


def sync_id_sequences(db: Session) -> None:
    """N3: rows created with a fixed id (the default store, older seeds' supplier #1) leave
    PostgreSQL's id counter behind, so the next POST tried id 1 again and failed with a 500.
    Move each counter past the largest id in use. SQLite needs nothing."""
    if db.get_bind().dialect.name != "postgresql":
        return
    for table, column in (("suppliers", "supplier_id"), ("stores", "store_id")):
        db.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
            f"GREATEST((SELECT COALESCE(MAX({column}), 0) FROM {table}), 1), "
            f"(SELECT COUNT(*) FROM {table}) > 0)"
        ))


def main() -> None:
    Base.metadata.create_all(engine)
    today, now = store_today(), datetime.now(timezone.utc)
    with SessionLocal() as db:
        ensure_default_store(db)
        sync_id_sequences(db)
        # Looked up by name and created without a fixed id (N3).
        supplier = db.scalar(select(Supplier).where(func.lower(Supplier.name) == SUPPLIER.lower()))
        if supplier is None:
            supplier = db.scalar(select(Supplier).order_by(Supplier.supplier_id).limit(1))
        if supplier is None:
            supplier = Supplier(name=SUPPLIER)
            db.add(supplier)
            db.flush()
        for sku, name, cat, unit, cost, price, shelf, batches in DEMO:
            if db.scalar(select(Product).where(Product.sku == sku)):
                continue
            p = Product(sku=sku, name=name, category=cat, unit=unit, shelf_life_days=shelf,
                        storage_type="Chilled", temp_min=2, temp_max=8, cost_price=Decimal(cost),
                        selling_price=Decimal(price))
            db.add(p)
            db.flush()
            for qty, ago, days in batches:
                db.add(Batch(product_id=p.product_id, supplier_id=supplier.supplier_id,
                             quantity=Decimal(qty), initial_quantity=Decimal(qty),
                             received_at=now - timedelta(days=ago),
                             expiry_date=today + timedelta(days=days)))
        db.commit()
    print("Demo products loaded: " + ", ".join(d[0] for d in DEMO))
    print("Log in with POST /api/auth/login to get a token.")


if __name__ == "__main__":
    main()
