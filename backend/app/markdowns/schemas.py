from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class MarkdownRuleCreate(BaseModel):
    productId: int | None = None
    category: str | None = None
    daysBeforeExpiry: int = Field(default=1, ge=0)
    discountPercent: Decimal = Field(..., gt=0)
    name: str | None = None


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
