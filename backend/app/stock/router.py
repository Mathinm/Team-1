
"""Stock counts (FR-9) and non-expiry removals (FR-13) - Issue #10."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Batch, Notification, Product, Removal, StockCount
from app.rbac import ADMIN, MANAGER, STAFF, CurrentUser, require_roles
from app.sales.fefo import UNITS_WHOLE_ONLY, check_quantity
from app.stock.schemas import RemovalIn, RemovalOut, StockCountIn, StockCountOut

router = APIRouter(prefix="/api", tags=["stock"])
inventory_users = require_roles(ADMIN, MANAGER, STAFF)


def _reason(value: str, max_len: int) -> str:
    reason = value.strip()
    if not reason or len(reason) > max_len:
        raise ApiError(
            400,
            "VALIDATION",
            f"reason must contain 1 to {max_len} characters",
        )
    return reason


def _batch(db: Session, batch_id: int) -> Batch:
    batch = db.scalar(
        select(Batch)
        .where(
            Batch.batch_id == batch_id,
            Batch.store_id == get_settings().store_id,
        )
        .with_for_update()
    )
    if batch is None:
        raise ApiError(404, "NOT_FOUND", "Unknown batch")
    return batch


def _check_unit_quantity(db: Session, batch: Batch, qty: Decimal) -> None:
    product = db.scalar(
        select(Product).where(
            Product.product_id == batch.product_id,
            Product.store_id == get_settings().store_id,
        )
    )
    if product is None:
        raise ApiError(404, "NOT_FOUND", "Unknown product")
    if product.unit in UNITS_WHOLE_ONLY and qty != qty.to_integral_value():
        raise ApiError(
            400,
            "INVALID",
            f"{product.name} requires a whole-number quantity",
        )


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


@router.post("/removals", status_code=201, response_model=RemovalOut)
def create_removal(
    body: RemovalIn,
    user: CurrentUser = Depends(inventory_users),
    db: Session = Depends(get_db),
):
    """FR-13: record damaged or temperature-breached stock and deduct it."""
    reason = _reason(body.reason, 40)
    qty = check_quantity(body.qty)
    batch = _batch(db, body.batchId)
    _check_unit_quantity(db, batch, qty)

    if qty > batch.quantity:
        raise ApiError(
            422,
            "INSUFFICIENT_STOCK",
            f"Insufficient stock: only {batch.quantity} available in this batch",
        )

    batch.quantity -= qty
    removal = Removal(
        store_id=get_settings().store_id,
        batch_id=batch.batch_id,
        quantity=qty,
        reason=reason,
        recorded_by=user.user_id,
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(removal)
    db.flush()

    # Record the notification in the same transaction as the stock removal.
    db.add(
        Notification(
            store_id=get_settings().store_id,
            batch_id=batch.batch_id,
            notification_type="removal",
            title="Stock removed",
            message=(
                f"Removed {qty} units from batch {batch.batch_id}. "
                f"Reason: {reason}."
            ),
        )
    )

    db.commit()
    db.refresh(removal)
    db.refresh(batch)

    return RemovalOut(
        removalId=removal.removal_id,
        batchId=batch.batch_id,
        qty=float(qty),
        reason=removal.reason,
        recordedBy=removal.recorded_by,
        recordedAt=_timestamp(removal.recorded_at),
        remainingQuantity=float(batch.quantity),
    )


@router.post("/stock-counts", status_code=201, response_model=StockCountOut)
def create_stock_count(
    body: StockCountIn,
    user: CurrentUser = Depends(inventory_users),
    db: Session = Depends(get_db),
):
    """FR-9: compare counted stock against the system quantity and audit the adjustment."""
    reason = _reason(body.reason, 255)

    # Zero is valid when the shelf is empty.
    counted = (
        Decimal("0")
        if body.countedQuantity == 0
        else check_quantity(body.countedQuantity)
    )

    batch = _batch(db, body.batchId)
    if counted > 0:
        _check_unit_quantity(db, batch, counted)

    system_qty = batch.quantity
    variance = counted - system_qty

    # The physical count becomes the new system quantity.
    batch.quantity = counted
    record = StockCount(
        store_id=get_settings().store_id,
        batch_id=batch.batch_id,
        system_quantity=system_qty,
        counted_quantity=counted,
        variance=variance,
        reason=reason,
        recorded_by=user.user_id,
        recorded_at=datetime.now(timezone.utc),
    )

    db.add(record)
    db.commit()
    db.refresh(record)
    db.refresh(batch)

    return StockCountOut(
        stockCountId=record.stock_count_id,
        batchId=batch.batch_id,
        systemQuantity=float(system_qty),
        countedQuantity=float(counted),
        variance=float(variance),
        reason=record.reason,
        recordedBy=record.recorded_by,
        recordedAt=_timestamp(record.recorded_at),
    )
