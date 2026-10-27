from decimal import Decimal

from pydantic import BaseModel, Field, StrictInt


class StockCountIn(BaseModel):
    batchId: StrictInt = Field(gt=0)
    countedQuantity: Decimal
    reason: str = Field(min_length=1, max_length=255)


class StockCountOut(BaseModel):
    stockCountId: int
    batchId: int
    systemQuantity: float
    countedQuantity: float
    variance: float
    reason: str
    recordedBy: str
    recordedAt: str


class RemovalIn(BaseModel):
    batchId: StrictInt = Field(gt=0)
    qty: Decimal
    reason: str = Field(min_length=1, max_length=40)


class RemovalOut(BaseModel):
    removalId: int
    batchId: int
    qty: float
    reason: str
    recordedBy: str
    recordedAt: str
    remainingQuantity: float
