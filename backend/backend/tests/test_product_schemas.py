from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.schemas import ProductCreate


def valid_payload(**overrides):
    data = {
        "store_id": 1,
        "name": "Tomato",
        "category": "Vegetables",
        "unit": "kg",
        "shelf_life_days": 5,
        "storage_type": "chilled",
        "min_temperature": Decimal("8"),
        "max_temperature": Decimal("12"),
        "cost_price": Decimal("20.00"),
        "selling_price": Decimal("30.00"),
    }
    data.update(overrides)
    return data


def test_default_low_stock_threshold_is_ten():
    product = ProductCreate(**valid_payload())
    assert product.low_stock_threshold == 10


def test_valid_product_is_accepted():
    product = ProductCreate(**valid_payload())
    assert product.name == "Tomato"
    assert product.unit == "kg"


@pytest.mark.parametrize("overrides", [
    {"shelf_life_days": 0},
    {"selling_price": Decimal("-5")},
    {"min_temperature": Decimal("12"), "max_temperature": Decimal("8")},
    {"unit": "box"},
    {"low_stock_threshold": -1},
])
def test_invalid_product_is_rejected(overrides):
    with pytest.raises(ValidationError):
        ProductCreate(**valid_payload(**overrides))
