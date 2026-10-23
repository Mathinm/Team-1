"""Store-scoped product and supplier master-data endpoints (Issue #5)."""

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Batch, Product, Supplier
from app.products.schemas import ProductCreate, ProductOut, ProductUpdate, SupplierOut
from app.rbac import ADMIN, MANAGER, CurrentUser, get_current_user, require_roles

router = APIRouter(prefix="/api", tags=["products"])
managers = require_roles(ADMIN, MANAGER)


def _product_out(db: Session, product: Product) -> ProductOut:
    total = db.scalar(
        select(func.coalesce(func.sum(Batch.quantity), 0)).where(
            Batch.product_id == product.product_id,
            Batch.store_id == product.store_id,
        )
    )
    return ProductOut(
        productId=product.product_id,
        sku=product.sku,
        name=product.name,
        category=product.category,
        unit=product.unit,
        shelfLifeDays=product.shelf_life_days,
        storageType=product.storage_type,
        tempMin=product.temp_min,
        tempMax=product.temp_max,
        costPrice=float(product.cost_price),
        sellingPrice=float(product.selling_price),
        lowStockThreshold=product.low_stock_threshold,
        active=product.active,
        stock=float(total or 0),
    )


def _find_product(db: Session, product_id: int) -> Product:
    product = db.scalar(
        select(Product).where(
            Product.product_id == product_id,
            Product.store_id == get_settings().store_id,
        )
    )
    if product is None:
        raise ApiError(404, "NOT_FOUND", "Product not found")
    return product


def _values(body: ProductCreate | ProductUpdate) -> dict:
    data = body.model_dump()
    return {
        "sku": data["sku"].strip(),
        "name": data["name"].strip(),
        "category": data["category"].strip(),
        "unit": data["unit"],
        "shelf_life_days": data["shelfLifeDays"],
        "storage_type": data["storageType"],
        "temp_min": data["tempMin"],
        "temp_max": data["tempMax"],
        "cost_price": Decimal(str(data["costPrice"])),
        "selling_price": Decimal(str(data["sellingPrice"])),
        "low_stock_threshold": data["lowStockThreshold"],
    }


@router.get("/products", response_model=list[ProductOut])
def list_products(
    _user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List this store's products, including inactive products and current stock."""
    products = db.scalars(
        select(Product)
        .where(Product.store_id == get_settings().store_id)
        .order_by(Product.product_id)
    )
    return [_product_out(db, product) for product in products]


@router.post("/products", status_code=201, response_model=ProductOut)
def create_product(
    body: ProductCreate,
    _user: CurrentUser = Depends(managers),
    db: Session = Depends(get_db),
):
    """Create a product; SKU is unique within the store."""
    values = _values(body)
    values["store_id"] = get_settings().store_id
    values["active"] = True
    product = Product(**values)
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "DUPLICATE_SKU", "A product with this SKU already exists") from None
    db.refresh(product)
    return _product_out(db, product)


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    body: ProductUpdate,
    _user: CurrentUser = Depends(managers),
    db: Session = Depends(get_db),
):
    product = _find_product(db, product_id)
    for field, value in _values(body).items():
        setattr(product, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "DUPLICATE_SKU", "A product with this SKU already exists") from None
    db.refresh(product)
    return _product_out(db, product)


@router.patch("/products/{product_id}/deactivate", response_model=ProductOut)
def deactivate_product(
    product_id: int,
    _user: CurrentUser = Depends(managers),
    db: Session = Depends(get_db),
):
    product = _find_product(db, product_id)
    product.active = False
    db.commit()
    db.refresh(product)
    return _product_out(db, product)


@router.patch("/products/{product_id}/activate", response_model=ProductOut)
def activate_product(
    product_id: int,
    _user: CurrentUser = Depends(managers),
    db: Session = Depends(get_db),
):
    product = _find_product(db, product_id)
    product.active = True
    db.commit()
    db.refresh(product)
    return _product_out(db, product)


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(
    _user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    suppliers = db.scalars(
        select(Supplier)
        .where(Supplier.store_id == get_settings().store_id)
        .order_by(Supplier.name)
    )
    return [SupplierOut(supplierId=s.supplier_id, name=s.name) for s in suppliers]
