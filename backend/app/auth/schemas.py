from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    userId: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)
    otpCode: str | None = None  # checked from S2-9 (2FA for Manager/Admin)


class LoginOut(BaseModel):
    token: str
    role: str
    expiresIn: int
    name: str
    userId: str


class MeOut(BaseModel):
    userId: str
    name: str
    role: str
    menu: list[str]  # screens this role may open (SEC-2)
