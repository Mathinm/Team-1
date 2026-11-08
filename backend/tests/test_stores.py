"""Stores table (NFR-14, TC-SCAL-01): more stores can be added without a schema change."""

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base
from app.models import Product, Store
from app.stores import ensure_default_store


@pytest.fixture()
def strict_db():
    """SQLite with foreign keys switched ON (PostgreSQL always enforces them)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    event.listen(engine, "connect", lambda c, _r: c.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def test_default_store_is_created_once_from_settings(strict_db):
    first = ensure_default_store(strict_db)
    again = ensure_default_store(strict_db)
    s = get_settings()
    assert (first.store_id, first.name, first.timezone) == (
        s.store_id, s.store_name, s.store_timezone)
    assert again.store_id == first.store_id
    assert len(strict_db.scalars(select(Store)).all()) == 1


def test_every_table_with_a_store_id_points_at_stores():
    insp = inspect(create_engine("sqlite://"))
    Base.metadata.create_all(insp.engine)
    missing = []
    for table in insp.get_table_names():
        if table == "stores" or "store_id" not in [c["name"] for c in insp.get_columns(table)]:
            continue
        targets = {(fk["constrained_columns"][0], fk["referred_table"])
                   for fk in insp.get_foreign_keys(table)}
        if ("store_id", "stores") not in targets:
            missing.append(table)
    assert missing == []


def test_a_second_store_needs_no_schema_change(strict_db):
    ensure_default_store(strict_db)
    strict_db.add(Store(store_id=2, name="Branch 2"))
    strict_db.flush()
    strict_db.add(Product(store_id=2, sku="TOM-01", name="Tomato", category="Veg", unit="kg",
                          shelf_life_days=5, storage_type="Chilled", temp_min=0, temp_max=8,
                          cost_price=20, selling_price=30))
    strict_db.flush()
    strict_db.add(Product(store_id=1, sku="TOM-01", name="Tomato", category="Veg", unit="kg",
                          shelf_life_days=5, storage_type="Chilled", temp_min=0, temp_max=8,
                          cost_price=20, selling_price=30))
    strict_db.flush()  # same SKU in two stores is fine


def test_data_for_an_unknown_store_is_refused(strict_db):
    ensure_default_store(strict_db)
    strict_db.add(Product(store_id=99, sku="X-1", name="X", category="Veg", unit="kg",
                          shelf_life_days=5, storage_type="Chilled", temp_min=0, temp_max=8,
                          cost_price=1, selling_price=1))
    with pytest.raises(IntegrityError):
        strict_db.flush()
