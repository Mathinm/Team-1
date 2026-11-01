"""S2-10 (#19): guards for the timing NFRs. The real measurements run against the whole stack
(perf/stock_latency.py, perf/alert_latency.py, perf/locustfile.py, CI job "docker"); these tests
stop a later change from quietly breaking them.

NFR-1 (TC-PERF-01): a stock change shows on every screen within 5 s.
NFR-2 (TC-PERF-02): an alert reaches staff within 60 s.
NFR-3 (TC-PERF-03): the products list stays fast with 5,000 batches.
"""

import asyncio
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import event

from app.config import Settings, get_settings
from app.models import Batch, Product
from app.notifications import service as expiry_service
from tests.conftest import auth

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def frontend_ms(file: str, name: str) -> int:
    """A refresh rate the web app really uses, e.g. LIVE_REFRESH_MS in lib/liveRefresh.js."""
    path = FRONTEND / file
    if not path.exists():
        pytest.skip(f"frontend not checked out ({path})")
    m = re.search(rf"{name}\s*=\s*(\d+)", path.read_text(encoding="utf-8"))
    assert m, f"{name} not found in {file}"
    return int(m.group(1))


# ---- NFR-1: visibility budget

# Locust (TC-PERF-03) fails the load test when 95% of requests take longer than this.
SLOW_REQUEST_S = 2.0


def test_nfr1_screen_refresh_keeps_stock_changes_within_5_s():
    """Worst case: the change lands just after a refresh, so it shows at the next refresh,
    which itself takes one request. Refresh interval + a slow request must be <= 5 s."""
    refresh_s = frontend_ms("lib/liveRefresh.js", "LIVE_REFRESH_MS") / 1000
    assert refresh_s + SLOW_REQUEST_S <= 5.0


def test_nfr1_stock_screens_use_live_refresh():
    for page in ("pages/ProductsPage.jsx", "pages/StockPage.jsx"):
        path = FRONTEND / page
        if not path.exists():
            pytest.skip("frontend not checked out")
        assert "useLiveRefresh(" in path.read_text(encoding="utf-8"), page


def test_nfr1_sale_is_in_the_products_list_at_once(client, seeded, pos_key):
    """The server side of NFR-1: the very next products request already shows the sale."""
    staff = auth("staff1", "Inventory Staff")
    before = next(p for p in client.get("/api/products", headers=staff).json()
                  if p["sku"] == "TOM-01")["stock"]
    r = client.post("/api/device/sales", headers={"X-Device-Key": pos_key},
                    json={"eventId": "nfr1-1", "sku": "TOM-01", "quantity": 2.5})
    assert r.status_code == 201
    after = next(p for p in client.get("/api/products", headers=staff).json()
                 if p["sku"] == "TOM-01")["stock"]
    assert after == before - 2.5 == r.json()["remainingStock"]


# ---- NFR-3: the products list (reloaded by every screen every 3 s) must not slow down as the
# catalogue grows. It used to run one stock query per product.


def _add_catalogue(db, products: int, batches_each: int) -> None:
    now = datetime.now(timezone.utc)
    for i in range(products):
        p = Product(sku=f"N-{i}", name=f"Item {i}", category="T", unit="kg",
                    shelf_life_days=5, storage_type="Chilled", temp_min=0, temp_max=8,
                    cost_price=Decimal(1), selling_price=Decimal(2))
        db.add(p)
        db.flush()
        db.add_all(Batch(product_id=p.product_id, supplier_id=1, quantity=Decimal(i + 1),
                         initial_quantity=Decimal(i + 1), received_at=now,
                         expiry_date=(now + timedelta(days=10)).date())
                   for _ in range(batches_each))
    db.commit()


def _count_queries(Session, client, headers) -> tuple[int, list]:
    engine = Session.kw["bind"]
    queries = []
    listener = lambda *args: queries.append(args[2])  # noqa: E731  (args[2] = the SQL text)
    event.listen(engine, "before_cursor_execute", listener)
    try:
        body = client.get("/api/products", headers=headers).json()
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(queries), body


def test_nfr3_products_list_query_count_does_not_grow_with_products(client, seeded, Session):
    staff = auth("staff1", "Inventory Staff")
    small, _ = _count_queries(Session, client, staff)
    with Session() as db:
        _add_catalogue(db, products=40, batches_each=3)
    large, body = _count_queries(Session, client, staff)
    assert large == small, f"{small} queries with 5 products, {large} with 45"
    assert len(body) == 45


def test_nfr3_products_list_stock_is_still_right(client, seeded, Session):
    """Same totals as before the one-query change, including a product with no batches."""
    with Session() as db:
        _add_catalogue(db, products=3, batches_each=4)  # stock 4, 8, 12
        db.add(Product(sku="EMPTY", name="No batches", category="T", unit="kg",
                       shelf_life_days=5, storage_type="Chilled", temp_min=0, temp_max=8,
                       cost_price=Decimal(1), selling_price=Decimal(2)))
        db.commit()
    stock = {p["sku"]: p["stock"]
             for p in client.get("/api/products", headers=auth("staff1", "Inventory Staff")).json()}
    assert stock["TOM-01"] == 37.0  # 12 + 25
    assert stock["MLK-01"] == 38.0  # expired 8 still counts as on hand, as before
    assert stock["OLD-01"] == 5.0  # inactive products are listed too
    assert (stock["N-0"], stock["N-1"], stock["N-2"]) == (4.0, 8.0, 12.0)
    assert stock["EMPTY"] == 0.0


# ---- NFR-2: delivery budget


def test_nfr2_worst_case_alert_time_is_within_60_s():
    """Low-stock, temperature and unit-failure alerts are raised in the request itself; expiry
    alerts by the expiry check. Then the scheduler sends them and the Alerts screen shows them
    at its next refresh. Worst case = all the waits added up."""
    s = get_settings()
    screen_s = frontend_ms("pages/AlertsPage.jsx", "REFRESH_MS") / 1000
    immediate = s.scheduler_interval_seconds + screen_s
    expiry = s.expiry_check_seconds + s.scheduler_interval_seconds + screen_s
    assert immediate <= 60
    assert expiry <= 60, f"expiry alerts could take {expiry} s"


def test_nfr2_expiry_check_runs_every_expiry_check_seconds(monkeypatch):
    """The expiry loop waits EXPIRY_CHECK_SECONDS between checks (it was a fixed 60 s)."""
    calls = []
    stop = asyncio.Event()

    def fake_check():
        calls.append(1)
        if len(calls) == 3:
            stop.set()
        return 0

    monkeypatch.setattr(expiry_service, "run_expiry_check", fake_check)
    monkeypatch.setattr(get_settings(), "expiry_check_seconds", 0)
    asyncio.run(asyncio.wait_for(expiry_service.run_notification_scheduler(stop), timeout=5))
    assert len(calls) == 3
    assert Settings.model_fields["expiry_check_seconds"].default <= 30
