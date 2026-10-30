"""Sales endpoints for people (Admin, Cashier). Devices use /api/device/sales instead."""

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.rbac import ADMIN, CASHIER, CurrentUser, require_roles
from app.sales.csv_import import import_sales_csv
from app.sales.fefo import record_sale
from app.sales.schemas import CsvResult, SaleIn, SaleOut, sale_out

router = APIRouter(prefix="/api/sales", tags=["sales"])
sellers = require_roles(ADMIN, CASHIER)


@router.post("", status_code=201, response_model=SaleOut)
def create_sale(body: SaleIn, user: CurrentUser = Depends(sellers), db: Session = Depends(get_db)):
    """FR-3 / FR-8: record a manual sale; stock is taken in FEFO order (422 on failure)."""
    result = record_sale(
        db,
        sku=body.sku,
        quantity=body.quantity,
        unit=body.unit,
        sold_at=body.soldAt,
        source="manual",
        recorded_by=user.user_id,
    )
    db.commit()
    return sale_out(result)


@router.post("/csv", response_model=CsvResult)
def upload_sales_csv(
    file: UploadFile | None = File(default=None),
    user: CurrentUser = Depends(sellers),
    db: Session = Depends(get_db),
):
    """FR-8: import many sales; bad rows are reported by line, good rows are kept."""
    if file is None:
        raise ApiError(400, "MISSING_FIELD", "Choose a CSV file")
    raw = file.file.read(1_000_001)
    return import_sales_csv(db, raw, recorded_by=user.user_id)
