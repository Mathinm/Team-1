"""TEST DATA for the performance checks (S2-10, #19): NFR-1, NFR-2, NFR-3.

Adds, to whatever database DATABASE_URL points at:
  - 100 products LT-001..LT-100, each with 50 batches              -> 5,000 batches (NFR-3)
  - 5 products LS-1..LS-5 kept near their low-stock threshold      -> low-stock alerts (NFR-2)
  - 100 sensor devices lt-sensor-001..100, one per fridge LT-F001.. -> 100 sensors (NFR-3)
  - 1 POS device lt-pos                                             -> simulator sales (NFR-1)
  - 50 users lt-user01..50 (half Inventory Staff, half Cashier)     -> 50 users (NFR-3)

Then prints JSON with the device keys and logins, which the scripts in perf/ read:

    docker compose exec -T backend python -m app.load_seed --yes > perf/seed.json

Safe to run again: existing rows are kept, and the device keys are replaced by new ones
(keys are stored only as hashes, so the old ones cannot be printed). Never run it against a
real store's database.
"""

import argparse
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.auth.passwords import hash_password
from app.db import Base, SessionLocal, engine
from app.device.auth import create_device, hash_key
from app.models import Batch, Device, Product, Supplier, User
from app.sales.fefo import store_today
from app.stores import ensure_default_store

PASSWORD = "LoadTest-2026"  # test accounts only
SUPPLIER = "Load Test Farms"


def _product(db, sku: str, name: str, threshold: int) -> tuple[Product, bool]:
    p = db.scalar(select(Product).where(Product.sku == sku))
    if p:
        return p, False
    p = Product(sku=sku, name=name, category="Load test", unit="kg", shelf_life_days=30,
                storage_type="Chilled", temp_min=0, temp_max=8, cost_price=Decimal(10),
                selling_price=Decimal(20), low_stock_threshold=threshold)
    db.add(p)
    db.flush()
    return p, True


def _device_key(db, name: str, kind: str) -> str:
    """Return a fresh key for the device, creating the device if needed."""
    device = db.scalar(select(Device).where(Device.name == name))
    if device is None:
        return create_device(db, name, kind)
    key = secrets.token_urlsafe(32)
    device.key_hash, device.active = hash_key(key), True
    return key


def seed(products: int, batches_each: int, sensors: int, users: int) -> dict:
    Base.metadata.create_all(engine)
    today, now = store_today(), datetime.now(timezone.utc)
    with SessionLocal() as db:
        ensure_default_store(db)
        supplier = db.scalar(select(Supplier).where(Supplier.name == SUPPLIER))
        if supplier is None:
            supplier = Supplier(name=SUPPLIER)
            db.add(supplier)
            db.flush()

        # Catalogue with lots of stock: never low, so it doesn't add alerts.
        for i in range(1, products + 1):
            p, new = _product(db, f"LT-{i:03d}", f"Load test item {i:03d}", threshold=10)
            if new:
                db.add_all(
                    Batch(product_id=p.product_id, supplier_id=supplier.supplier_id,
                          quantity=Decimal(1000), initial_quantity=Decimal(1000),
                          received_at=now - timedelta(days=1),
                          expiry_date=today + timedelta(days=5 + b % 25))
                    for b in range(batches_each)
                )

        # Low-stock alert products: perf/alert_latency.py tops them up to 12 and sells 3.
        low_stock = []
        for i in range(1, 6):
            p, new = _product(db, f"LS-{i}", f"Low-stock test {i}", threshold=10)
            if new:
                db.add(Batch(product_id=p.product_id, supplier_id=supplier.supplier_id,
                             quantity=Decimal(12), initial_quantity=Decimal(12),
                             received_at=now - timedelta(days=1),
                             expiry_date=today + timedelta(days=20)))
            low_stock.append({"sku": p.sku, "productId": p.product_id, "threshold": 10})

        sensor_list = [
            {"unitId": f"LT-F{i:03d}", "key": _device_key(db, f"lt-sensor-{i:03d}", "sensor")}
            for i in range(1, sensors + 1)
        ]
        pos_key = _device_key(db, "lt-pos", "pos")

        password_hash = None
        user_list = []
        for i in range(1, users + 1):
            user_id = f"lt-user{i:02d}"
            role = "Inventory Staff" if i % 2 else "Cashier"
            if db.scalar(select(User).where(User.user_id == user_id)) is None:
                password_hash = password_hash or hash_password(PASSWORD)
                db.add(User(user_id=user_id, name=f"Load Tester {i:02d}",
                            email=f"{user_id}@example.com", role=role,
                            password_hash=password_hash))
            user_list.append({"userId": user_id, "role": role})

        db.commit()
        total_batches = db.scalar(select(func.count()).select_from(Batch))
        return {
            "password": PASSWORD,
            "supplierId": supplier.supplier_id,
            "users": user_list,
            "posKey": pos_key,
            "sensors": sensor_list,
            "loadSkus": [f"LT-{i:03d}" for i in range(1, products + 1)],
            "lowStock": low_stock,
            "totalBatches": total_batches,
        }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yes", action="store_true", help="really add the test data")
    ap.add_argument("--products", type=int, default=100)
    ap.add_argument("--batches-each", type=int, default=50)
    ap.add_argument("--sensors", type=int, default=100)
    ap.add_argument("--users", type=int, default=50)
    args = ap.parse_args(argv)
    if not args.yes:
        print(__doc__)
        print("Nothing done. Add --yes to create the test data.", file=sys.stderr)
        return 2
    data = seed(args.products, args.batches_each, args.sensors, args.users)
    print(json.dumps(data, indent=1))
    print(f"Seeded: {data['totalBatches']} batches in the database, {len(data['sensors'])} "
          f"sensors, {len(data['users'])} users.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
