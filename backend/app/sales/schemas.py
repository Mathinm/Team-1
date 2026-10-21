from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.sales.fefo import SaleResult


class SaleIn(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    quantity: Decimal
    unit: str | None = Field(default=None, max_length=10)
    soldAt: datetime | None = None


class BatchUsedOut(BaseModel):
    batchId: int
    qty: float
    expiryDate: date


class SaleOut(BaseModel):
    saleId: int
    batchesUsed: list[BatchUsedOut]
    remainingStock: float
    productName: str
    unit: str
    amount: float


def sale_out(r: SaleResult) -> SaleOut:
    return SaleOut(
        saleId=r.sale_id,
        batchesUsed=[
            BatchUsedOut(batchId=b.batch_id, qty=float(b.qty), expiryDate=b.expiry_date)
            for b in r.batches_used
        ],
        remainingStock=float(r.remaining_stock),
        productName=r.product_name,
        unit=r.unit,
        amount=float(r.amount),
    )


class CsvError(BaseModel):
    line: int
    message: str


class CsvResult(BaseModel):
    imported: int
    failed: int
    errors: list[CsvError]
