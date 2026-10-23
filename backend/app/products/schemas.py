"""Request and response schemas for the product master API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Unit = Literal["kg", "piece", "l"]
StorageType = str


class ProductFields(BaseModel):
    sku: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=40)
    unit: Unit
    shelfLifeDays: int = Field(ge=1, le=3650)
    storageType: StorageType
    tempMin: float = Field(ge=-60, le=100)
    tempMax: float = Field(ge=-60, le=100)
    costPrice: float = Field(ge=0)
    sellingPrice: float = Field(ge=0)
    lowStockThreshold: int = Field(default=10, ge=0)

    @model_validator(mode="after")
    def validate_temperature_range(self):
        if self.tempMin > self.tempMax:
            raise ValueError("tempMin must be less than or equal to tempMax")
        return self


class ProductCreate(ProductFields):
    pass


class ProductUpdate(ProductFields):
    pass


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    productId: int
    sku: str
    name: str
    category: str
    unit: str
    shelfLifeDays: int
    storageType: str
    tempMin: float
    tempMax: float
    costPrice: float
    sellingPrice: float
    lowStockThreshold: int
    active: bool
    stock: float


class SupplierOut(BaseModel):
    supplierId: int
    name: str
