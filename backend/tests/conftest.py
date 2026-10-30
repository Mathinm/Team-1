import os

os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")
os.environ.setdefault("STORE_TIMEZONE", "Asia/Kolkata")
os.environ.setdefault("SCHEDULER_ENABLED", "false")  # tests call the scheduler jobs directly

from datetime import datetime, timedelta, timezone  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth.passwords import hash_password  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.device.auth import create_device  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Batch, Product, Supplier, User, UserSession  # noqa: E402
from app.rbac import create_access_token  # noqa: E402
from app.sales.fefo import store_today  # noqa: E402

_current: dict = {}  # the test's session factory, so auth() can create users and sessions


@pytest.fixture()
def Session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    _current["Session"] = factory
    return factory


@pytest.fixture()
def db(Session):
    with Session() as s:
        yield s


@pytest.fixture()
def client(Session):
    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _product(pid, sku, name, unit, price, active=True):
    return Product(
        product_id=pid, sku=sku, name=name, category="Test", unit=unit, shelf_life_days=5,
        storage_type="Chilled", temp_min=2, temp_max=8, cost_price=Decimal("1"),
        selling_price=Decimal(str(price)), active=active,
    )


@pytest.fixture()
def seeded(db):
    """Same shop as the frontend demo data: tomato 12 kg (2 days) + 25 kg (5 days),
    milk with an expired 8 l batch + 30 l, bread with only an expired batch, banana by piece."""
    today = store_today()
    now = datetime.now(timezone.utc)

    def batch(bid, pid, qty, expires_in):
        return Batch(
            batch_id=bid, product_id=pid, supplier_id=1, quantity=Decimal(str(qty)),
            initial_quantity=Decimal(str(qty)), received_at=now - timedelta(days=2),
            expiry_date=today + timedelta(days=expires_in),
        )

    db.add(Supplier(supplier_id=1, name="Fresh Farms"))
    db.add_all([
        _product(1, "TOM-01", "Tomato", "kg", 30),
        _product(2, "BAN-01", "Banana", "piece", 6),
        _product(3, "MLK-01", "Milk 1L", "l", 28),
        _product(5, "BRD-01", "Bread Loaf", "piece", 40),
        _product(6, "OLD-01", "Retired item", "kg", 10, active=False),
    ])
    db.flush()
    db.add_all([
        batch(101, 1, 12, 2), batch(102, 1, 25, 5),
        batch(103, 2, 60, 4),
        batch(104, 3, 8, -1), batch(105, 3, 30, 3),
        batch(107, 5, 7, -1),
        batch(108, 6, 5, 3),
    ])
    db.commit()
    return db


PASSWORD = "Passw0rd!"


def make_user(user_id, role, password=PASSWORD, active=True):
    """Create (or update the role of) a user in the test database."""
    with _current["Session"]() as s:
        user = s.query(User).filter_by(user_id=user_id).one_or_none()
        if user is None:
            user = User(user_id=user_id, name=user_id, email=f"{user_id}@example.com",
                        role=role, password_hash=hash_password(password), active=active)
            s.add(user)
        else:
            user.role = role
        s.commit()
        return user.id


def auth(user_id="cashier1", role="Cashier"):
    """Header for a logged-in user: creates the user and an open session, like a real login."""
    user_pk = make_user(user_id, role)
    sid = f"test-{user_id}-{os.urandom(4).hex()}"
    with _current["Session"]() as s:
        s.add(UserSession(sid=sid, user_pk=user_pk))
        s.commit()
    return {"Authorization": f"Bearer {create_access_token(user_id, role, user_id, sid=sid)}"}


def login(client, user_id, password=PASSWORD):
    return client.post("/api/auth/login", json={"userId": user_id, "password": password})


@pytest.fixture()
def cashier(Session):
    return auth()


@pytest.fixture()
def pos_key(db):
    return create_device(db, "pos-1", "pos")


@pytest.fixture()
def sensor_key(db):
    return create_device(db, "sensors-1", "sensor")


def stock(db, product_id):
    from sqlalchemy import func, select

    db.expire_all()
    return db.scalar(select(func.sum(Batch.quantity)).where(Batch.product_id == product_id))
