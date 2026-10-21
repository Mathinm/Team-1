"""Sales: FEFO deduction, expired-batch blocking, manual and CSV (FR-3, FR-7, FR-8)."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Batch, Sale, SaleBatch
from app.sales.fefo import store_today
from tests.conftest import auth, stock


def sell(client, headers, **body):
    return client.post("/api/sales", json=body, headers=headers)


# ---- FEFO (TC-STK-04, TC-STK-05, TC-STK-12) ---------------------------------------------
def test_takes_stock_from_earliest_expiring_batch(client, seeded, cashier):
    r = sell(client, cashier, sku="TOM-01", quantity=5, unit="kg")
    assert r.status_code == 201
    body = r.json()
    assert [(b["batchId"], b["qty"]) for b in body["batchesUsed"]] == [(101, 5)]
    assert body["batchesUsed"][0]["expiryDate"] == str(store_today() + timedelta(days=2))
    assert body["remainingStock"] == 32
    assert body["productName"] == "Tomato" and body["unit"] == "kg"
    assert body["amount"] == 150.0 and isinstance(body["saleId"], int)


def test_sale_spanning_two_batches(client, seeded, cashier):
    r = sell(client, cashier, sku="TOM-01", quantity=15)
    assert [(b["batchId"], b["qty"]) for b in r.json()["batchesUsed"]] == [(101, 12), (102, 3)]
    assert stock(seeded, 1) == 22


def test_fractional_quantity_and_amount_rounding(client, seeded, cashier):
    r = sell(client, cashier, sku="TOM-01", quantity=0.333)
    assert r.status_code == 201
    assert r.json()["amount"] == 9.99  # 0.333 * 30
    assert stock(seeded, 1) == Decimal("36.667")


def test_sale_is_recorded_with_audit_trail(client, seeded, cashier):
    sell(client, cashier, sku="TOM-01", quantity=15)
    seeded.expire_all()
    sale = seeded.scalars(select(Sale)).one()
    assert (sale.source, sale.recorded_by, sale.unit_price) == ("manual", "cashier1", 30)
    lines = seeded.scalars(select(SaleBatch).order_by(SaleBatch.batch_id)).all()
    assert [(line.batch_id, line.quantity) for line in lines] == [(101, 12), (102, 3)]
    assert sum(line.quantity for line in lines) == sale.quantity


def test_sku_is_case_and_space_insensitive(client, seeded, cashier):
    assert sell(client, cashier, sku="  tom-01 ", quantity=1).status_code == 201


# ---- stock limits (TC-STK-06) -----------------------------------------------------------
def test_insufficient_stock_is_rejected_and_nothing_changes(client, seeded, cashier):
    r = sell(client, cashier, sku="TOM-01", quantity=40)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert r.json()["error"]["message"] == "Insufficient stock: only 37 kg available"
    assert stock(seeded, 1) == 37
    assert seeded.scalar(select(func.count()).select_from(Sale)) == 0


def test_selling_exactly_all_stock_works(client, seeded, cashier):
    r = sell(client, cashier, sku="TOM-01", quantity=37)
    assert r.status_code == 201 and r.json()["remainingStock"] == 0
    assert sell(client, cashier, sku="TOM-01", quantity=1).status_code == 422


# ---- expired batches (TC-STK-10, TC-STK-11, FR-7) ---------------------------------------
def test_expired_batch_is_never_sold_from(client, seeded, cashier):
    r = sell(client, cashier, sku="MLK-01", quantity=4)
    assert [b["batchId"] for b in r.json()["batchesUsed"]] == [105]
    assert stock(seeded, 3) == 34  # 8 expired + 26 left; expired batch untouched
    assert seeded.get(Batch, 104).quantity == 8


def test_only_expired_stock_is_blocked_with_batch_expired(client, seeded, cashier):
    r = sell(client, cashier, sku="BRD-01", quantity=2)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "BATCH_EXPIRED"
    assert seeded.get(Batch, 107).quantity == 7


def test_quantity_above_unexpired_stock_counts_expired_as_unavailable(client, seeded, cashier):
    r = sell(client, cashier, sku="MLK-01", quantity=31)  # 30 fresh + 8 expired
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert "only 30 l available" in r.json()["error"]["message"]


def test_batch_is_sellable_on_its_expiry_date_not_after(db, seeded):
    from app.sales.fefo import record_sale

    today = store_today()
    seeded.get(Batch, 101).expiry_date = today
    seeded.get(Batch, 102).expiry_date = today - timedelta(days=1)
    seeded.commit()
    res = record_sale(seeded, sku="TOM-01", quantity=12, source="manual", recorded_by="t")
    assert [b.batch_id for b in res.batches_used] == [101]
    seeded.commit()
    try:
        record_sale(seeded, sku="TOM-01", quantity=1, source="manual", recorded_by="t")
    except Exception as e:  # noqa: BLE001
        assert e.code == "BATCH_EXPIRED"
    else:
        raise AssertionError("expired batch was sold")


def test_ties_on_expiry_use_oldest_batch_first(client, seeded, cashier):
    seeded.get(Batch, 102).expiry_date = seeded.get(Batch, 101).expiry_date
    seeded.commit()
    r = sell(client, cashier, sku="TOM-01", quantity=13)
    assert [b["batchId"] for b in r.json()["batchesUsed"]] == [101, 102]


# ---- validation -------------------------------------------------------------------------
def test_unknown_sku_404(client, seeded, cashier):
    r = sell(client, cashier, sku="NOPE-1", quantity=1)
    assert r.status_code == 404 and r.json()["error"]["message"] == "Unknown SKU NOPE-1"


def test_inactive_product_422(client, seeded, cashier):
    r = sell(client, cashier, sku="OLD-01", quantity=1)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INACTIVE"


def test_bad_quantities_are_400_and_change_nothing(client, seeded, cashier):
    for q in (0, -5, "abc", 0.0005, 1e9):
        r = sell(client, cashier, sku="TOM-01", quantity=q)
        assert r.status_code == 400, q
        assert "error" in r.json()
    assert stock(seeded, 1) == 37


def test_pieces_must_be_whole_numbers(client, seeded, cashier):
    assert sell(client, cashier, sku="BAN-01", quantity=2.5).status_code == 400
    assert sell(client, cashier, sku="BAN-01", quantity=2).status_code == 201


def test_unit_must_match_product(client, seeded, cashier):
    r = sell(client, cashier, sku="TOM-01", quantity=1, unit="piece")
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNIT_MISMATCH"


def test_missing_fields_use_error_envelope_with_400(client, seeded, cashier):
    r = client.post("/api/sales", json={"quantity": 1}, headers=cashier)
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "VALIDATION" and "sku" in err["message"]


# ---- roles (SEC-2) ----------------------------------------------------------------------
def test_requires_login(client, seeded):
    r = client.post("/api/sales", json={"sku": "TOM-01", "quantity": 1})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Your session has ended. Please log in again."


def test_garbage_and_tampered_tokens_are_rejected(client, seeded, cashier):
    tampered = {"Authorization": cashier["Authorization"] + "x"}
    for h in ({"Authorization": "Bearer nonsense"}, tampered):
        r = client.post("/api/sales", json={"sku": "TOM-01", "quantity": 1}, headers=h)
        assert r.status_code == 401


def test_expired_session_is_rejected(client, seeded):
    from app.rbac import create_access_token

    h = {"Authorization": f"Bearer {create_access_token('c', 'Cashier', expires_in=-10)}"}
    assert client.post("/api/sales", json={"sku": "TOM-01", "quantity": 1}, headers=h
                       ).status_code == 401


def test_only_admin_and_cashier_may_sell(client, seeded):
    body = {"sku": "TOM-01", "quantity": 1}
    for user, role, expected in [("m", "Manager", 403), ("s", "Inventory Staff", 403),
                                 ("c", "Cashier", 201), ("a", "Admin", 201)]:
        r = client.post("/api/sales", json=body, headers=auth(user, role))
        assert r.status_code == expected
    r = client.post("/api/sales", json=body, headers=auth("m", "Manager"))
    assert r.json()["error"]["code"] == "FORBIDDEN"


# ---- CSV (TC-STK-13, TC-STK-14) ---------------------------------------------------------
def upload(client, headers, content, name="sales.csv"):
    if isinstance(content, str):
        content = content.encode()
    return client.post("/api/sales/csv", files={"file": (name, content, "text/csv")},
                       headers=headers)


def test_csv_imports_valid_rows_and_reports_bad_ones_by_line(client, seeded, cashier):
    r = upload(client, cashier, "sku,quantity\nTOM-01,1\nNOPE-1,2\nBAN-01,3\n")
    assert r.status_code == 200
    assert r.json() == {"imported": 2, "failed": 1,
                        "errors": [{"line": 3, "message": "Unknown SKU NOPE-1"}]}
    assert stock(seeded, 1) == 36 and stock(seeded, 2) == 57


def test_csv_20_valid_rows(client, seeded, cashier):
    r = upload(client, cashier, "sku,quantity\n" + "TOM-01,1\n" * 20)
    assert r.json() == {"imported": 20, "failed": 0, "errors": []}
    assert stock(seeded, 1) == 17


def test_csv_rows_deduct_in_fefo_order_and_later_rows_see_earlier_ones(client, seeded, cashier):
    # 12 kg expire first; rows 1+2 drain that batch, row 3 must come from the next one.
    r = upload(client, cashier, "sku,quantity\nTOM-01,10\nTOM-01,2\nTOM-01,5\n")
    assert r.json()["imported"] == 3
    seeded.expire_all()
    assert seeded.get(Batch, 101).quantity == 0 and seeded.get(Batch, 102).quantity == 20


def test_csv_stock_errors_are_per_row(client, seeded, cashier):
    r = upload(client, cashier, "sku,quantity\nTOM-01,30\nTOM-01,30\nBRD-01,1\n")
    errs = r.json()["errors"]
    assert r.json()["imported"] == 1
    assert [(e["line"], e["message"].split(":")[0]) for e in errs] == [
        (3, "Insufficient stock"), (4, "Batch expired")]


def test_csv_handles_excel_quirks(client, seeded, cashier):
    text = (
        "\ufeffSKU , Quantity,SoldAt\r\n\r\n"
        "tom-01,1,2026-10-19\r\nBAN-01, 2 ,2026-10-19T09:30\r\n"
    )
    r = upload(client, cashier, text)
    assert r.json() == {"imported": 2, "failed": 0, "errors": []}
    sold = seeded.scalars(select(Sale).order_by(Sale.sale_id)).all()
    assert sold[0].sold_at.date().isoformat() in ("2026-10-18", "2026-10-19")  # IST midnight


def test_csv_bad_sold_at_and_bad_quantity_are_row_errors(client, seeded, cashier):
    r = upload(client, cashier, "sku,quantity,soldAt\nTOM-01,1,yesterday\nTOM-01,x,\nTOM-01,,\n")
    assert r.json()["imported"] == 0
    assert [e["line"] for e in r.json()["errors"]] == [2, 3, 4]
    assert stock(seeded, 1) == 37


def test_csv_requires_sku_and_quantity_columns(client, seeded, cashier):
    for content in ("code,qty\nTOM-01,1\n", "", "\n\n"):
        r = upload(client, cashier, content)
        assert r.status_code == 400
        assert r.json()["error"]["message"] == "CSV must have the columns sku and quantity"


def test_csv_rejects_binary_and_missing_file(client, seeded, cashier):
    assert upload(client, cashier, b"\xff\xfe\x00bad").status_code == 400
    r = client.post("/api/sales/csv", headers=cashier)
    assert r.status_code == 400 and r.json()["error"]["message"] == "Choose a CSV file"


def test_csv_role_check(client, seeded):
    assert upload(client, auth("m", "Manager"), "sku,quantity\nTOM-01,1\n").status_code == 403
    assert upload(client, {}, "sku,quantity\nTOM-01,1\n").status_code == 401
