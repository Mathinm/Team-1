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


@lru_cache
def get_settings() -> Settings:
    return Settings()
