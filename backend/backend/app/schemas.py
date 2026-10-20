from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class StoreOut(StoreCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=100)
    unit: Literal["kg", "piece", "litre"]
    shelf_life_days: int = Field(gt=0)
    storage_type: str = Field(min_length=1, max_length=40)
    min_temperature: Decimal
    max_temperature: Decimal
    cost_price: Decimal = Field(ge=0)
    selling_price: Decimal = Field(gt=0)
    low_stock_threshold: int = Field(default=10, ge=0)

    @model_validator(mode="after")
    def check_temps(self):
        if self.min_temperature >= self.max_temperature:
            raise ValueError("min_temperature must be less than max_temperature")
        return self


class ProductCreate(ProductBase):
    store_id: int = Field(gt=0)


class ProductUpdate(ProductBase):
    pass


class ProductOut(ProductBase):
    id: int
    store_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Compatibility names used by the Issue #5 router modules.
StoreRead = StoreOut
ProductRead = ProductOut
