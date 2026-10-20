from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Store
from app.schemas import StoreCreate, StoreRead

router = APIRouter(prefix="/stores", tags=["stores"])


@router.post("", response_model=StoreRead, status_code=status.HTTP_201_CREATED)
def create_store(payload: StoreCreate, db: Session = Depends(get_db)):
    store = Store(name=payload.name.strip())
    db.add(store)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A store with this name already exists")
    db.refresh(store)
    return store


@router.get("", response_model=list[StoreRead])
def list_stores(db: Session = Depends(get_db)):
    return db.scalars(select(Store).order_by(Store.id)).all()
