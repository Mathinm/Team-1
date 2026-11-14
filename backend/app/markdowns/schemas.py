from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class MarkdownRuleCreate(BaseModel):
    productId: int | None = Field(default=None, gt=0, le=2_147_483_647)
    category: str | None = Field(default=None, max_length=40)
    daysBeforeExpiry: int = Field(default=1, ge=0, le=365)
    discountPercent: Decimal = Field(..., gt=0, decimal_places=2)
    name: str | None = Field(default=None, max_length=120)

    @field_validator("category")
    @classmethod
    def _category_not_blank(cls, value: str | None) -> str | None:
        # A blank category would save a rule that matches nothing, so refuse it.
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class MarkdownRuleOut(BaseModel):
    ruleId: int
    productId: int | None = None
    category: str | None = None
    daysBeforeExpiry: int
    discountPercent: float
    name: str = ""
    active: bool = True
    createdBy: str
    createdAt: datetime


class MarkdownOut(BaseModel):
    markdownId: int
    batchId: int
    productId: int
    productName: str
    sku: str
    originalPrice: float
    discountPercent: float
    discountedPrice: float
    initialQuantity: float
    quantitySold: float
    remainingQuantity: float
    sellThroughPercent: float
    status: str
    markedDownAt: datetime


class MarkdownApplyResponse(BaseModel):
    applied: int
    markdowns: list[MarkdownOut]
