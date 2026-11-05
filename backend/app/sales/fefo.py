"""FEFO deduction and sale recording (FR-3, FR-7, FR-8). Shared by manual, CSV and device sales.

One sale = one database transaction (the caller commits). The eligible batches are row-locked
(SELECT ... FOR UPDATE) so concurrent sales cannot oversell or break FEFO order (SAD 3.7).

Rules, matching the frontend mock backend:
  * A batch is sellable through its expiry date (inclusive), judged on the store's calendar day
    of the sale itself (soldAt), so late-arriving offline sales are not refused after midnight.
  * Earliest expiry first; ties by batch id (older first).
  * Nothing sellable but stock exists  -> 422 BATCH_EXPIRED.
  * Quantity above sellable stock      -> 422 INSUFFICIENT_STOCK (nothing is deducted).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.alerts.service import refresh_after_change
from app.config import get_settings
from app.errors import ApiError
from app.markdowns.service import get_active_batch_markdown, record_markdown_sale
from app.models import Batch, Product, Sale, SaleBatch

MAX_QTY = Decimal("999999.999")
UNITS_WHOLE_ONLY = {"piece"}
CLOCK_SKEW = timedelta(minutes=5)  # a POS clock may run a little fast; more than this is junk
_PLAIN_NUMBER = re.compile(r"[+]?(\d+(\.\d*)?|\.\d+)")


@dataclass
class BatchUsed:
    batch_id: int
    qty: Decimal
    expiry_date: date


@dataclass
class SaleResult:
    sale_id: int
    product_name: str
    unit: str
    amount: Decimal
    batches_used: list[BatchUsed]
    remaining_stock: Decimal


def store_today(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo(get_settings().store_timezone)).date()


def to_utc(dt: datetime) -> datetime:
    """Naive times are taken as store-local time; aware times are converted to UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(get_settings().store_timezone))
    return dt.astimezone(timezone.utc)


def fmt_qty(q: Decimal) -> str:
    return format(q.normalize(), "f")


def check_quantity(value) -> Decimal:
    """Parse and validate a quantity (>0, at most 3 decimals). Raises 400."""
    try:
        if isinstance(value, Decimal):
            qty = value
        else:
            text = str(value).strip()
            # Decimal() also accepts "1_0" (= 10) and "1e2"; a typo must not become a sale.
            if not _PLAIN_NUMBER.fullmatch(text):
                raise ValueError(text)
            qty = Decimal(text)
    except Exception:
        raise ApiError(400, "INVALID", f"Quantity must be a number (got '{value}')") from None
    if not qty.is_finite() or qty <= 0:
        raise ApiError(400, "INVALID", "Quantity must be greater than 0")
    if qty > MAX_QTY:
        raise ApiError(400, "INVALID", f"Quantity must be at most {MAX_QTY}")
    if qty != qty.quantize(Decimal("0.001")):
        raise ApiError(400, "INVALID", "Quantity can have at most 3 decimal places")
    return qty


def record_sale(
    db: Session,
    *,
    sku: str,
    quantity,
    unit: str | None = None,
    sold_at: datetime | None = None,
    source: str,
    recorded_by: str,
    device_id: int | None = None,
    event_id: str | None = None,
    now: datetime | None = None,
) -> SaleResult:
    now = now or datetime.now(timezone.utc)
    store_id = get_settings().store_id
    sku_key = (sku or "").strip().upper()
    if not sku_key:
        raise ApiError(400, "INVALID", "SKU and a quantity greater than 0 are required")
    qty = check_quantity(quantity)

    product = db.scalar(
        select(Product).where(Product.store_id == store_id, func.upper(Product.sku) == sku_key)
    )
    if product is None:
        raise ApiError(404, "NOT_FOUND", f"Unknown SKU {str(sku).strip()}")
    if not product.active:
        raise ApiError(422, "INACTIVE", f"{product.name} is deactivated")
    if unit and unit.strip().lower() != product.unit:
        raise ApiError(
            400, "UNIT_MISMATCH", f"{product.name} is sold in {product.unit}, not {unit.strip()}"
        )
    if product.unit in UNITS_WHOLE_ONLY and qty != qty.to_integral_value():
        msg = f"{product.name} is sold by the {product.unit}: use a whole number"
        raise ApiError(400, "INVALID", msg)

    sold_at_utc = to_utc(sold_at) if sold_at else now
    if sold_at_utc > now + CLOCK_SKEW:
        raise ApiError(400, "INVALID", "Sale time cannot be in the future")

    # Expiry is judged on the day the sale HAPPENED, not the day it was received: a POS sale
    # made yesterday and sent after an outage still counts as made while the batch was valid.
    today = store_today(sold_at_utc)
    # Lock every batch with stock for this product, in FEFO order (same order for every
    # caller, so concurrent sales queue up instead of deadlocking).
    batches = db.scalars(
        select(Batch)
        .where(Batch.product_id == product.product_id, Batch.quantity > 0)
        .order_by(Batch.expiry_date, Batch.batch_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    total = sum((b.quantity for b in batches), Decimal(0))
    eligible = [b for b in batches if b.expiry_date >= today]
    sellable = sum((b.quantity for b in eligible), Decimal(0))

    if sellable <= 0 and total > 0:
        raise ApiError(422, "BATCH_EXPIRED", "Batch expired: no unexpired stock to sell")
    if qty > sellable:
        raise ApiError(
            422,
            "INSUFFICIENT_STOCK",
            f"Insufficient stock: only {fmt_qty(sellable)} {product.unit} available",
        )

    left = qty
    used: list[BatchUsed] = []
    total_amount = Decimal("0.00")
    for b in eligible:
        if left <= 0:
            break
        take = min(b.quantity, left)
        b.quantity -= take
        left -= take
        used.append(BatchUsed(b.batch_id, take, b.expiry_date))

        # Check if batch has an active markdown (FR-14, TC-EXP-08)
        md = get_active_batch_markdown(db, b.batch_id)
        if md is not None:
            batch_unit_price = md.discounted_price
            record_markdown_sale(db, b.batch_id, take)
        else:
            batch_unit_price = product.selling_price
        total_amount += take * batch_unit_price

    amount = total_amount.quantize(Decimal("0.01"), ROUND_HALF_UP)
    avg_unit_price = (amount / qty).quantize(Decimal("0.01"), ROUND_HALF_UP)
    sale = Sale(
        store_id=store_id,
        product_id=product.product_id,
        sku=product.sku,
        quantity=qty,
        unit=product.unit,
        unit_price=avg_unit_price,
        amount=amount,
        sold_at=sold_at_utc,
        source=source,
        recorded_by=recorded_by,
        device_id=device_id,
        event_id=event_id,
    )
    db.add(sale)
    db.flush()  # assigns sale_id; a duplicate (device_id, event_id) fails here
    db.add_all(SaleBatch(sale_id=sale.sale_id, batch_id=u.batch_id, quantity=u.qty) for u in used)
    db.flush()
    refresh_after_change(db, product.product_id)  # FR-11: below threshold -> LOW_STOCK alert

    remaining = total - qty  # on hand across all batches, expired included (matches product.stock)
    return SaleResult(sale.sale_id, product.name, product.unit, amount, used, remaining)
