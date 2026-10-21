"""Sales CSV upload (FR-8, UC-18): columns sku, quantity, soldAt (optional).

Valid rows are imported and bad rows are reported with their line number; each row is its
own transaction, so one bad row never blocks or rolls back the others.
"""

import csv
import io
from datetime import datetime

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.sales.fefo import record_sale
from app.sales.schemas import CsvError, CsvResult

MAX_BYTES = 1_000_000  # nginx in front of the API also limits bodies to 1 MB
MAX_ROWS = 5000
NEEDS = "CSV must have the columns sku and quantity"


def _parse_sold_at(text: str) -> datetime | None:
    text = text.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise ApiError(
            400, "INVALID", f"Invalid soldAt '{text}': use e.g. 2026-10-20 or 2026-10-20T14:30"
        ) from None


def import_sales_csv(db: Session, raw: bytes, *, recorded_by: str) -> CsvResult:
    if len(raw) > MAX_BYTES:
        raise ApiError(400, "INVALID", "The CSV file is too large (limit 1 MB)")
    try:
        text = raw.decode("utf-8-sig")  # Excel adds a BOM
    except UnicodeDecodeError:
        raise ApiError(400, "INVALID", "The file must be UTF-8 text saved as CSV") from None

    reader = csv.reader(io.StringIO(text, newline=""))
    headers: list[str] | None = None
    for row in reader:
        if any(c.strip() for c in row):
            headers = [c.strip().lower() for c in row]
            break
    if headers is None or "sku" not in headers or "quantity" not in headers:
        raise ApiError(400, "INVALID", NEEDS)
    col = {h: i for i, h in enumerate(headers)}

    def cell(row: list[str], name: str) -> str:
        i = col.get(name)
        return row[i].strip() if i is not None and i < len(row) else ""

    imported = 0
    errors: list[CsvError] = []
    rows = 0
    for row in reader:
        if not any(c.strip() for c in row):
            continue
        rows += 1
        if rows > MAX_ROWS:
            raise ApiError(400, "INVALID", f"The CSV has more than {MAX_ROWS} rows: split the file")
        line = reader.line_num
        try:
            record_sale(
                db,
                sku=cell(row, "sku"),
                quantity=cell(row, "quantity"),
                sold_at=_parse_sold_at(cell(row, "soldat")),
                source="csv",
                recorded_by=recorded_by,
            )
            db.commit()
            imported += 1
        except ApiError as e:
            db.rollback()
            errors.append(CsvError(line=line, message=e.message))
    return CsvResult(imported=imported, failed=len(errors), errors=errors)
