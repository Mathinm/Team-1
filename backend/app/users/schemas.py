from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Role = Literal["Admin", "Manager", "Inventory Staff", "Cashier"]


class UserCreate(BaseModel):
    userId: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: Role
    password: str = Field(min_length=8, max_length=128)  # first password, set by the Admin


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    role: Role | None = None


class UserOut(BaseModel):
    userId: str
    name: str
    email: str
    role: str
    active: bool
    storeId: int
