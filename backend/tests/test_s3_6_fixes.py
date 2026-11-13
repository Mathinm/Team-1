"""Sprint 3 fixes from issue #69 (S3-6): sale prices per batch (T8), duplicate CSV files
(N10), markdowns ended by removals and counts (N8), category rule checks (N11), removal
messages (N16, N21). Back-dated sales (N1) are tested in test_sales.py."""

from decimal import Decimal

from sqlalchemy import func, select

from app.models import Markdown, Notification, Sale
from tests.conftest import auth, stock


def mgr():
    return auth("mgr69", "Manager")


def staff():
    return auth("staff69", "Inventory Staff")


def mark_down_tomato(client, pct=25):
    """Tomato B-101 (12 kg, 2 days left) and B-102 (25 kg, 5 days) at 30/kg; 3-day rule."""
    h = mgr()
    r = client.post("/api/markdown-rules", headers=h,
                    json={"productId": 1, "daysBeforeExpiry": 3, "discountPercent": pct})
    assert r.status_code == 201, r.json()
    assert client.post("/api/markdowns/apply", headers=h).status_code == 200


# ---- T8: each batch line shows what it was billed at --------------------------------
def test_sale_lists_price_per_batch_with_markdown(client, seeded, cashier):
    mark_down_tomato(client)
    r = client.post("/api/sales", headers=cashier, json={"sku": "TOM-01", "quantity": 14})
    assert r.status_code == 201
    used = r.json()["batchesUsed"]
    assert used[0] == {**used[0], "batchId": 101, "qty": 12, "unitPrice": 22.5,
                       "originalPrice": 30.0, "discountPercent": 25.0}
    assert used[1] == {**used[1], "batchId": 102, "qty": 2, "unitPrice": 30.0,
                       "originalPrice": 30.0, "discountPercent": None}
    assert r.json()["amount"] == 12 * 22.5 + 2 * 30


def test_sale_without_markdown_has_normal_price(client, seeded, cashier):
    r = client.post("/api/sales", headers=cashier, json={"sku": "BAN-01", "quantity": 3})
    b = r.json()["batchesUsed"][0]
    assert (b["unitPrice"], b["originalPrice"], b["discountPercent"]) == (6.0, 6.0, None)


# ---- N10: the same CSV file is imported once ----------------------------------------
def upload(client, headers, content):
    return client.post("/api/sales/csv", headers=headers,
                       files={"file": ("sales.csv", content, "text/csv")})


def test_same_csv_file_twice_is_refused_and_sells_nothing_more(client, seeded, cashier, Session):
    content = "sku,quantity\nTOM-01,1\nBAN-01,2\n"
    assert upload(client, cashier, content).json()["imported"] == 2
    r = upload(client, cashier, content)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "DUPLICATE_FILE"
    assert "already imported" in r.json()["error"]["message"]
    with Session() as s:
        assert s.scalar(select(func.count()).select_from(Sale)) == 2
    assert stock(seeded, 1) == 36


def test_a_different_file_still_imports(client, seeded, cashier):
    assert upload(client, cashier, "sku,quantity\nTOM-01,1\n").json()["imported"] == 1
    assert upload(client, cashier, "sku,quantity\nTOM-01,2\n").json()["imported"] == 1
    assert stock(seeded, 1) == 34


def test_file_where_every_row_failed_can_be_sent_again(client, seeded, cashier):
    content = "sku,quantity\nNOPE-1,1\n"
    assert upload(client, cashier, content).json()["imported"] == 0
    assert upload(client, cashier, content).status_code == 200


# ---- N8: a batch emptied by a removal or a count is no longer on markdown -----------
def markdown_status(db, batch_id):
    db.expire_all()
    return db.scalar(select(Markdown.status).where(Markdown.batch_id == batch_id))


def test_removing_a_marked_down_batch_ends_its_markdown(client, seeded):
    mark_down_tomato(client)
    r = client.post("/api/removals", headers=staff(),
                    json={"batchId": 101, "qty": 12, "reason": "Damaged"})
    assert r.status_code == 201, r.json()
    assert markdown_status(seeded, 101) == "ended"
    listed = {m["batchId"]: m["status"] for m in
              client.get("/api/markdowns", headers=mgr()).json()}
    assert listed[101] == "ended"


def test_counting_a_marked_down_batch_to_zero_ends_its_markdown(client, seeded):
    mark_down_tomato(client)
    r = client.post("/api/stock-counts", headers=staff(),
                    json={"batchId": 101, "countedQuantity": 0, "reason": "Shelf empty"})
    assert r.status_code == 201, r.json()
    assert markdown_status(seeded, 101) == "ended"


def test_partial_removal_keeps_the_markdown(client, seeded):
    mark_down_tomato(client)
    client.post("/api/removals", headers=staff(),
                json={"batchId": 101, "qty": 2, "reason": "Damaged"})
    assert markdown_status(seeded, 101) == "active"


# ---- N11: category rules must name a real category ----------------------------------
def test_unknown_category_rule_is_refused(client, seeded):
    r = client.post("/api/markdown-rules", headers=mgr(),
                    json={"category": "Daiyr", "daysBeforeExpiry": 2, "discountPercent": 10})
    assert r.status_code == 400
    assert "Unknown category 'Daiyr'" in r.json()["error"]["message"]


def test_category_is_matched_ignoring_case(client, seeded):
    r = client.post("/api/markdown-rules", headers=mgr(),
                    json={"category": "test", "daysBeforeExpiry": 2, "discountPercent": 10})
    assert r.status_code == 201


def test_product_with_a_different_category_is_refused(client, seeded):
    r = client.post("/api/markdown-rules", headers=mgr(), json={
        "productId": 1, "category": "Bakery", "daysBeforeExpiry": 2, "discountPercent": 10})
    assert r.status_code == 400
    assert "choose the product or the category" in r.json()["error"]["message"]


# ---- N16 / N21: removal messages ----------------------------------------------------
def test_removal_over_stock_message_is_readable(client, seeded):
    r = client.post("/api/removals", headers=staff(),
                    json={"batchId": 101, "qty": 13, "reason": "Damaged"})
    assert r.status_code == 422
    assert r.json()["error"]["message"] == "Insufficient stock: only 12 kg left in B-101"


def test_removal_notification_names_the_batch_like_the_screens(client, seeded):
    client.post("/api/removals", headers=staff(),
                json={"batchId": 101, "qty": Decimal("1.5").__str__(), "reason": "Damaged"})
    seeded.expire_all()
    msg = seeded.scalar(select(Notification.message).where(
        Notification.notification_type == "removal"))
    assert msg == "Removed 1.5 kg from B-101. Reason: Damaged."


# ---- N7: products say how much can actually be sold ---------------------------------
def test_products_show_sellable_stock_without_expired_batches(client, seeded, cashier):
    by_sku = {p["sku"]: p for p in client.get("/api/products", headers=cashier).json()}
    assert (by_sku["MLK-01"]["stock"], by_sku["MLK-01"]["sellableStock"]) == (38, 30)
    assert (by_sku["BRD-01"]["stock"], by_sku["BRD-01"]["sellableStock"]) == (7, 0)
    assert by_sku["TOM-01"]["sellableStock"] == 37
