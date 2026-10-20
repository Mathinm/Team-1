from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, Store
from app.schemas import ProductCreate, ProductRead, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])


def get_product_in_store(db: Session, product_id: int, store_id: int) -> Product:
    product = db.scalar(
        select(Product).where(Product.id == product_id, Product.store_id == store_id)
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found for this store")
    return product


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    store = db.get(Store, payload.store_id)
    if store is None or not store.is_active:
        raise HTTPException(status_code=404, detail="Active store not found")

    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("", response_model=list[ProductRead])
def list_products(
    store_id: int = Query(gt=0),
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    query = select(Product).where(Product.store_id == store_id)
    if not include_inactive:
        query = query.where(Product.is_active.is_(True))
    return db.scalars(query.order_by(Product.id)).all()


@router.get("/{product_id}", response_model=ProductRead)
def read_product(product_id: int, store_id: int = Query(gt=0), db: Session = Depends(get_db)):
    return get_product_in_store(db, product_id, store_id)


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    store_id: int = Query(gt=0),
    db: Session = Depends(get_db),
):
    product = get_product_in_store(db, product_id, store_id)
    if not product.is_active:
        raise HTTPException(status_code=409, detail="Deactivated products cannot be edited")
    for field, value in payload.model_dump().items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.post("/{product_id}/deactivate", response_model=ProductRead)
def deactivate_product(product_id: int, store_id: int = Query(gt=0), db: Session = Depends(get_db)):
    product = get_product_in_store(db, product_id, store_id)
    product.is_active = False
    db.commit()
    db.refresh(product)
    return product


@router.post("/{product_id}/reactivate", response_model=ProductRead)
def reactivate_product(product_id: int, store_id: int = Query(gt=0), db: Session = Depends(get_db)):
    product = get_product_in_store(db, product_id, store_id)
    product.is_active = True
    db.commit()
    db.refresh(product)
    return product
