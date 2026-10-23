"""Batches (FR-2, FR-4, FR-5, FR-6): receive stock, restock, and list batches in FEFO order.

Rules, matching the frontend mock backend (frontend/src/api/mock/handlers.js):
  * Quantity > 0 with at most 3 decimals; `piece` products need whole numbers.
  * The expiry date may not be before the day the batch was received (store calendar day).
  * A restock has no expiry label of its own: expiry = today + the product's shelf-life.
  * The FEFO list shows every batch that still has stock, expired ones included, earliest
    expiry first (ties: older batch first), so staff can see what to sell and what to remove.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.batches.schemas import BatchCreated, BatchIn, FefoBatchOut, RestockIn
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Batch, Product, Supplier
from app.rbac import ADMIN, MANAGER, STAFF, CurrentUser, get_current_user, require_roles
from app.sales.fefo import UNITS_WHOLE_ONLY, check_quantity, store_today, to_utc

router = APIRouter(prefix="/api", tags=["batches"])
receivers = require_roles(ADMIN, MANAGER, STAFF)


def _find_product(db: Session, product_id: int) -> Product:
    product = db.scalar(
        select(Product).where(
            Product.product_id == product_id,
            Product.store_id == get_settings().store_id,
        )
    )
    if product is None:
        raise ApiError(404, "NOT_FOUND", "Unknown product")
    return product


def _find_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.scalar(
        select(Supplier).where(
            Supplier.supplier_id == supplier_id,
            Supplier.store_id == get_settings().store_id,
        )
    )
    if supplier is None:
        raise ApiError(400, "INVALID", "Unknown supplier")
    return supplier


def _check_receivable(product: Product, quantity, unit: str | None) -> Decimal:
    """Shared checks for a new batch and a restock. Returns the parsed quantity."""
    if not product.active:
        raise ApiError(422, "INACTIVE", f"{product.name} is deactivated")
    qty = check_quantity(quantity)
    if unit and unit.strip().lower() != product.unit:
        raise ApiError(
            400, "UNIT_MISMATCH", f"{product.name} is stocked in {product.unit}, not {unit.strip()}"
        )
    if product.unit in UNITS_WHOLE_ONLY and qty != qty.to_integral_value():
        msg = f"{product.name} is stocked by the {product.unit}: use a whole number"
        raise ApiError(400, "INVALID", msg)
    return qty


def _aware(dt: datetime) -> datetime:
    """Stored times are UTC; SQLite hands them back without a timezone."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _received_day(received_at: datetime) -> date:
    """Store calendar day on which a batch was received."""
    return store_today(_aware(received_at))


def _stock(db: Session, product_id: int) -> float:
    total = db.scalar(
        select(func.coalesce(func.sum(Batch.quantity), 0)).where(Batch.product_id == product_id)
    )
    return float(total or 0)


@router.post("/batches", status_code=201, response_model=BatchCreated)
def receive_batch(
    body: BatchIn,
    _user: CurrentUser = Depends(receivers),
    db: Session = Depends(get_db),
):
    """FR-2: record a delivery with its supplier, quantity, received time and expiry date."""
    product = _find_product(db, body.productId)
    supplier = _find_supplier(db, body.supplierId)
    qty = _check_receivable(product, body.quantity, body.unit)
    received_at = to_utc(body.receivedAt)
    if body.expiryDate < _received_day(received_at):
        raise ApiError(400, "INVALID", "Expiry date must be after received date")
    batch = Batch(
        store_id=get_settings().store_id,
        product_id=product.product_id,
        supplier_id=supplier.supplier_id,
        quantity=qty,
        initial_quantity=qty,
        received_at=received_at,
        expiry_date=body.expiryDate,
    )
    db.add(batch)
    db.commit()
    return BatchCreated(batchId=batch.batch_id, newStock=_stock(db, product.product_id))


@router.post("/restocks", status_code=201, response_model=BatchCreated)
def restock(
    body: RestockIn,
    _user: CurrentUser = Depends(receivers),
    db: Session = Depends(get_db),
):
    """FR-4: add stock without its own expiry label; expiry comes from the shelf-life."""
    product = _find_product(db, body.productId)
    qty = _check_receivable(product, body.quantity, body.unit)
    if body.supplierId is not None:
        supplier_id = _find_supplier(db, body.supplierId).supplier_id
    else:
        supplier_id = db.scalar(
            select(Batch.supplier_id)
            .where(Batch.product_id == product.product_id)
            .order_by(Batch.received_at.desc(), Batch.batch_id.desc())
            .limit(1)
        )
        if supplier_id is None:
            msg = "No earlier batch to take the supplier from: choose a supplier"
            raise ApiError(400, "MISSING_FIELD", msg)
    today = store_today()
    batch = Batch(
        store_id=get_settings().store_id,
        product_id=product.product_id,
        supplier_id=supplier_id,
        quantity=qty,
        initial_quantity=qty,
        received_at=datetime.now(timezone.utc),
        expiry_date=today + timedelta(days=product.shelf_life_days),
    )
    db.add(batch)
    db.commit()
    return BatchCreated(batchId=batch.batch_id, newStock=_stock(db, product.product_id))


@router.get("/batches/fefo", response_model=list[FefoBatchOut])
def fefo_order(
    productId: int,
    _user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """FR-5, FR-6: batches with stock, earliest expiry first, with age and days left."""
    product = _find_product(db, productId)
    today = store_today()
    rows = db.execute(
        select(Batch, Supplier.name)
        .join(Supplier, Supplier.supplier_id == Batch.supplier_id)
        .where(Batch.product_id == product.product_id, Batch.quantity > 0)
        .order_by(Batch.expiry_date, Batch.batch_id)
    ).all()
    return [
        FefoBatchOut(
            batchId=b.batch_id,
            quantity=float(b.quantity),
            unit=product.unit,
            supplier=supplier_name,
            receivedAt=_aware(b.received_at),
            expiryDate=b.expiry_date,
            daysInStore=(today - _received_day(b.received_at)).days,
            daysToExpiry=(b.expiry_date - today).days,
        )
        for b, supplier_name in rows
    ]
