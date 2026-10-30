"""Alerts module (SAD 3.4, ADR-7): the only place that creates, resolves and stores alerts.

Other modules call raise_alert()/resolve_alert() instead of writing to the alerts table
themselves. Delivery to people is in notifier.py and happens after the alert is stored, so an
alert stays visible in the app even when delivery fails.

Low-stock rules (SRS 4.3):
  * FR-11  an item whose stock falls BELOW its threshold raises LOW_STOCK at once (checked after
           every sale, removal, stock count, batch/restock and threshold edit). Exactly at the
           threshold is not an alert. The alert closes by itself when stock is back at or above it.
  * FR-10  once a day (scheduler) an item whose stock minus its average daily sales of the last
           7 days would be below the threshold tomorrow raises PROJECTED_LOW_STOCK.
"stock" is the same number the Products screen shows: everything on hand in all batches.
"""

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert, Batch, JobRun, Product, Sale

log = logging.getLogger("pms.alerts")

LOW_STOCK = "LOW_STOCK"
PROJECTED_LOW_STOCK = "PROJECTED_LOW_STOCK"
UNIT_FAILURE = "UNIT_FAILURE"
DOOR_OPEN = "DOOR_OPEN"
TEMPERATURE = "TEMPERATURE"

AVG_SALES_DAYS = 7  # FR-10: projection uses the average daily sales of the last 7 days
LOW_STOCK_JOB = "daily_low_stock_check"


# ------------------------------------------------------------------ small helpers
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite hands datetimes back without a timezone; everything is stored in UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def store_day(now: datetime) -> date:
    return now.astimezone(ZoneInfo(get_settings().store_timezone)).date()


def fmt(q) -> str:
    """12.000 -> '12', 2.50 -> '2.5' (for messages)."""
    return format(Decimal(str(q)).normalize(), "f")


def guarded(db: Session, fn: Callable, *args, **kwargs):
    """Run an alert check without ever breaking the caller.

    A sale, removal or sensor reading must still be saved if alert evaluation fails (SAD 3.7:
    core stock functions do not depend on alerts), so errors are logged and rolled back to a
    savepoint instead of being raised.
    """
    try:
        with db.begin_nested():
            return fn(db, *args, **kwargs)
    except Exception:
        log.exception("Alert check failed and was skipped: %s", getattr(fn, "__name__", fn))
        return None


# ------------------------------------------------------------------ create / resolve
def raise_alert(
    db: Session,
    *,
    type: str,
    key: str,
    message: str,
    severity: str = "warning",
    product_id: int | None = None,
    unit_id: str | None = None,
    triggered_at: datetime | None = None,
) -> Alert | None:
    """Create an alert unless one with the same key is still open. Returns the new alert or None.

    `key` names the condition (e.g. "low_stock:7", "door_open:Fridge-1"); it is what stops the
    same problem from being reported again and again until it has been resolved.
    """
    store_id = get_settings().store_id
    if db.scalar(select(Alert.alert_id).where(Alert.store_id == store_id, Alert.open_key == key)):
        return None
    alert = Alert(
        store_id=store_id, type=type, severity=severity, message=message[:255],
        product_id=product_id, unit_id=unit_id, open_key=key, status="active",
        triggered_at=as_utc(triggered_at) or now_utc(), delivery_status="pending",
    )
    try:
        with db.begin_nested():
            db.add(alert)
            db.flush()
    except IntegrityError:  # another request raised the same alert a moment ago
        return None
    log.info("ALERT_RAISED type=%s key=%s message=%s", type, key, message)
    return alert


def resolve_alert(
    db: Session, key: str, reason: str, *, resolved_at: datetime | None = None
) -> Alert | None:
    """Close the open alert with this key (the condition has ended). Kept in the history."""
    store_id = get_settings().store_id
    alert = db.scalar(
        select(Alert).where(Alert.store_id == store_id, Alert.open_key == key).with_for_update()
    )
    if alert is None:
        return None
    alert.status = "resolved"
    alert.open_key = None
    alert.resolved_at = as_utc(resolved_at) or now_utc()
    alert.resolution = reason[:255]
    log.info("ALERT_RESOLVED id=%s key=%s reason=%s", alert.alert_id, key, reason)
    return alert


# ------------------------------------------------------------------ low stock (FR-11)
def total_stock(db: Session, product_id: int) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Batch.quantity), 0)).where(Batch.product_id == product_id)
    )
    return Decimal(str(total or 0))


def refresh_stock_alerts(
    db: Session, product: Product, *, stock: Decimal | None = None, now: datetime | None = None
) -> Alert | None:
    """Raise LOW_STOCK when stock < threshold, close it when stock is back at/above it.

    Call this inside the transaction that changed the stock (before commit). Returns the new
    alert, if one was raised.
    """
    now = now or now_utc()
    stock = total_stock(db, product.product_id) if stock is None else Decimal(str(stock))
    threshold = product.low_stock_threshold
    low_key = f"low_stock:{product.product_id}"
    projected_key = f"projected:{product.product_id}"

    if product.active and stock < threshold:
        # A real shortage replaces the "will run low" warning.
        resolve_alert(db, projected_key, "Stock is now below the threshold", resolved_at=now)
        message = (f"{product.name} is low: {fmt(stock)} {product.unit} left "
                   f"(threshold {threshold})")
        return raise_alert(
            db, type=LOW_STOCK, key=low_key, message=message, severity="warning",
            product_id=product.product_id, triggered_at=now,
        )
    reason = (f"Stock is back to {fmt(stock)} {product.unit}" if product.active
              else f"{product.name} was deactivated")
    resolve_alert(db, low_key, reason, resolved_at=now)
    return None


# ------------------------------------------------------------------ projected low stock (FR-10)
def average_daily_sales(db: Session, product_id: int, now: datetime) -> Decimal:
    """Quantity sold in the last 7 days divided by 7 (days without sales count as 0)."""
    since = now - timedelta(days=AVG_SALES_DAYS)
    sold = db.scalar(
        select(func.coalesce(func.sum(Sale.quantity), 0)).where(
            Sale.product_id == product_id, Sale.sold_at >= since, Sale.sold_at <= now
        )
    )
    return Decimal(str(sold or 0)) / AVG_SALES_DAYS


def run_low_stock_check(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Alert Service operation runLowStockCheck() (SAD 4.3). Idempotent: safe to run twice.

    1. makes sure every active item already below its threshold has its LOW_STOCK alert;
    2. raises PROJECTED_LOW_STOCK where  stock - average daily sales < threshold  while stock is
       still at or above the threshold; closes projected alerts that no longer apply.
    The caller commits.
    """
    now = now or now_utc()
    store_id = get_settings().store_id
    raised = resolved = 0
    products = db.scalars(
        select(Product).where(Product.store_id == store_id, Product.active.is_(True))
        .order_by(Product.product_id)
    ).all()
    for product in products:
        stock = total_stock(db, product.product_id)
        threshold = product.low_stock_threshold
        if refresh_stock_alerts(db, product, stock=stock, now=now):
            raised += 1
        key = f"projected:{product.product_id}"
        if stock < threshold:
            continue  # already handled as a real shortage
        avg = average_daily_sales(db, product.product_id, now)
        if avg > 0 and stock - avg < threshold:
            message = (f"{product.name} projected below {threshold} tomorrow "
                       f"({fmt(stock)} {product.unit} now, about {fmt(round(avg, 2))} "
                       f"{product.unit} sold per day)")
            if raise_alert(db, type=PROJECTED_LOW_STOCK, key=key, message=message,
                           severity="warning", product_id=product.product_id, triggered_at=now):
                raised += 1
        elif resolve_alert(db, key, "Projection no longer below the threshold", resolved_at=now):
            resolved += 1
    return {"raised": raised, "resolved": resolved}


def run_daily_low_stock_job(db: Session, now: datetime | None = None) -> bool:
    """Run the daily check once per store day, at or after LOW_STOCK_CHECK_TIME.

    The last run day is stored in the database, so a restart neither skips nor repeats the job.
    Returns True when it ran. The caller commits.
    """
    now = now or now_utc()
    settings = get_settings()
    local = now.astimezone(ZoneInfo(settings.store_timezone))
    try:
        hh, mm = (int(x) for x in settings.low_stock_check_time.split(":"))
    except ValueError:
        log.error("LOW_STOCK_CHECK_TIME must look like 06:00 (got %r)",
                  settings.low_stock_check_time)
        return False
    if (local.hour, local.minute) < (hh, mm):
        return False
    today = local.date()
    row = db.scalar(select(JobRun).where(JobRun.store_id == settings.store_id,
                                         JobRun.job == LOW_STOCK_JOB))
    if row is not None and row.last_run_on >= today:
        return False
    try:
        with db.begin_nested():
            if row is None:
                db.add(JobRun(store_id=settings.store_id, job=LOW_STOCK_JOB, last_run_on=today))
            else:
                row.last_run_on = today
            db.flush()
    except IntegrityError:  # another instance claimed today's run first
        return False
    result = run_low_stock_check(db, now)
    log.info("Daily low-stock check ran: %s", result)
    return True


def refresh_after_change(db: Session, product_id: int) -> None:
    """Hook for every code path that changes a product's stock or threshold.

    Call it inside the same transaction, after the change and before commit. It never raises:
    the sale, removal, count or edit is saved even if alert evaluation fails.
    """

    def _refresh(db: Session, product_id: int) -> None:
        db.flush()  # so the stock sum sees the change that was just made
        product = db.get(Product, product_id)
        if product is not None:
            refresh_stock_alerts(db, product)

    guarded(db, _refresh, product_id)
