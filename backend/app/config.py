"""Settings read from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://pms:password@localhost:5432/pms"
    # Shared secret for the HS256 session tokens. Empty = every token is rejected.
    jwt_secret: str = ""
    # Every store record carries a store ID (NFR-14). One store for now.
    store_id: int = 1
    # "Expires today" is judged on the store's calendar day, not the server's (UTC in Docker).
    store_timezone: str = "Asia/Kolkata"

    # ---- Login (SEC-1, #3)
    # How long a login token stays valid.
    token_expire_minutes: int = 60
    # First Admin, created at startup only when there are no users yet.
    admin_user_id: str = "admin"
    admin_password: str = "admin123"
    admin_email: str = "admin@example.com"
    # Also create manager1 / staff1 / cashier1 (the frontend demo logins). Dev and demo only.
    seed_demo_users: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
