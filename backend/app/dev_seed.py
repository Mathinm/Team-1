"""DEV ONLY: load the frontend's demo shop, so the sales and device endpoints can be tried
before products/batches (#5, #6) are merged. Log in with POST /api/auth/login to get a token
(cashier1/cashier123 with SEED_DEMO_USERS=true, or the Admin from .env).

    docker compose exec backend python -m app.dev_seed

Safe to run twice (existing SKUs are skipped). Delete this file once #5/#6 are in.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import Batch, Product, Supplier
from app.sales.fefo import store_today

# sku, name, category, unit, price, [(quantity, days until expiry), ...]
DEMO = [
    ("TOM-01", "Tomato", "Vegetables", "kg", 30, [(12, 2), (25, 5)]),
    ("BAN-01", "Banana", "Fruits", "piece", 6, [(60, 4)]),
    ("MLK-01", "Milk 1L", "Dairy", "l", 28, [(8, -1), (30, 3)]),  # first batch already expired
    ("BRD-01", "Bread Loaf", "Bakery", "piece", 40, [(7, -1)]),  # only expired stock
]


def main() -> None:
    Base.metadata.create_all(engine)
    today, now = store_today(), datetime.now(timezone.utc)
    with SessionLocal() as db:
        if db.get(Supplier, 1) is None:
            db.add(Supplier(supplier_id=1, name="Fresh Farms"))
            db.flush()
        for sku, name, cat, unit, price, batches in DEMO:
            if db.scalar(select(Product).where(Product.sku == sku)):
                continue
            p = Product(sku=sku, name=name, category=cat, unit=unit, shelf_life_days=5,
                        storage_type="Chilled", temp_min=2, temp_max=8, cost_price=Decimal(1),
                        selling_price=Decimal(price))
            db.add(p)
            db.flush()
            for qty, days in batches:
                db.add(Batch(product_id=p.product_id, supplier_id=1, quantity=Decimal(qty),
                             initial_quantity=Decimal(qty), received_at=now - timedelta(days=2),
                             expiry_date=today + timedelta(days=days)))
        db.commit()
    print("Demo products loaded: " + ", ".join(d[0] for d in DEMO))
    print("Log in with POST /api/auth/login to get a token.")


if __name__ == "__main__":
    main()
