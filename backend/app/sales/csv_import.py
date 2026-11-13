"""Sales CSV upload (FR-8, UC-18): columns sku, quantity, soldAt (optional).

Valid rows are imported and bad rows are reported with their line number; each row is its
own transaction, so one bad row never blocks or rolls back the others.
"""

import csv
import hashlib
import io
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError
from app.models import CsvImport
from app.sales.fefo import max_backdate, record_sale
from app.sales.schemas import CsvError, CsvResult

MAX_BYTES = 1_000_000  # nginx in front of the API also limits bodies to 1 MB
MAX_ROWS = 5000
NEEDS = "CSV must have the columns sku and quantity"
BAD_CSV = "The file is not a valid CSV (a cell is far too long or the text is damaged)"


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


def _check_not_imported(db: Session, store_id: int, digest: str) -> None:
    """N10: the same file (byte for byte) is imported only once."""
    done = db.scalar(
        select(CsvImport).where(CsvImport.store_id == store_id, CsvImport.file_sha256 == digest)
    )
    if done is not None:
        when = done.imported_at.strftime("%d %b %Y %H:%M") if done.imported_at else "earlier"
        raise ApiError(
            409,
            "DUPLICATE_FILE",
            f"This file was already imported ({when}, {done.imported} sales by "
            f"{done.recorded_by}). Nothing was imported again.",
        )


def import_sales_csv(db: Session, raw: bytes, *, recorded_by: str) -> CsvResult:
    if len(raw) > MAX_BYTES:
        raise ApiError(400, "INVALID", "The CSV file is too large (limit 1 MB)")
    store_id = get_settings().store_id
    digest = hashlib.sha256(raw).hexdigest()
    _check_not_imported(db, store_id, digest)
    try:
        text = raw.decode("utf-8-sig")  # Excel adds a BOM
    except UnicodeDecodeError:
        raise ApiError(400, "INVALID", "The file must be UTF-8 text saved as CSV") from None

    reader = csv.reader(io.StringIO(text, newline=""))
    headers: list[str] | None = None
    try:
        for row in reader:
            if any(c.strip() for c in row):
                headers = [c.strip().lower() for c in row]
                break
    except csv.Error:
        raise ApiError(400, "INVALID", BAD_CSV) from None
    if headers is None or "sku" not in headers or "quantity" not in headers:
        raise ApiError(400, "INVALID", NEEDS)
    col = {h: i for i, h in enumerate(headers)}

    def cell(row: list[str], name: str) -> str:
        i = col.get(name)
        return row[i].strip() if i is not None and i < len(row) else ""

    # Read every data row first and enforce the limit BEFORE saving anything, so an over-long
    # file is refused as a whole (nothing imported) and re-uploading it in parts never doubles.
    data_rows: list[tuple[int, list[str]]] = []
    try:
        for row in reader:
            if not any(c.strip() for c in row):
                continue
            if len(data_rows) >= MAX_ROWS:
                raise ApiError(
                    400, "INVALID", f"The CSV has more than {MAX_ROWS} rows: split the file"
                )
            data_rows.append((reader.line_num, row))
    except csv.Error:
        raise ApiError(400, "INVALID", BAD_CSV) from None

    imported = 0
    errors: list[CsvError] = []
    for line, row in data_rows:
        try:
            record_sale(
                db,
                sku=cell(row, "sku"),
                quantity=cell(row, "quantity"),
                sold_at=_parse_sold_at(cell(row, "soldat")),
                source="csv",
                recorded_by=recorded_by,
                max_age=max_backdate(),
            )
            db.commit()
            imported += 1
        except ApiError as e:
            db.rollback()
            errors.append(CsvError(line=line, message=e.message))
    if imported:
        # A file where every row failed may be fixed in the shop (stock received) and sent
        # again, so only a file that imported something is remembered.
        db.add(CsvImport(store_id=store_id, file_sha256=digest, imported=imported,
                         recorded_by=recorded_by))
        db.commit()
    return CsvResult(imported=imported, failed=len(errors), errors=errors)
