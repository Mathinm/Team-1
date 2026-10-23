"""Request and response schemas for batches, restocks and the FEFO list."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class BatchIn(BaseModel):
    productId: int
    supplierId: int
    quantity: Decimal
    unit: str | None = Field(default=None, max_length=10)
    receivedAt: datetime
    expiryDate: date


class RestockIn(BaseModel):
    productId: int
    quantity: Decimal
    unit: str | None = Field(default=None, max_length=10)
    supplierId: int | None = None  # default: the supplier of this product's latest batch


class BatchCreated(BaseModel):
    batchId: int
    newStock: float


class FefoBatchOut(BaseModel):
    batchId: int
    quantity: float
    unit: str
    supplier: str
    receivedAt: datetime
    expiryDate: date
    daysInStore: int
    daysToExpiry: int
