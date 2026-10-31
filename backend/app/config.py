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

    # ---- Account protection (SEC-3, #18)
    # The account locks after this many wrong passwords in a row; an Admin unlocks it.
    max_failed_logins: int = 5
    # A session with no request for this long is ended (idle logout).
    idle_timeout_minutes: int = 30

    # ---- Two-factor login for Manager and Admin by emailed code (NFR-10, #18)
    require_2fa: bool = True
    otp_expire_minutes: int = 10
    # Asking again sooner than this does not send another email.
    otp_resend_seconds: int = 30

    # ---- Password reset by email (SEC-5, #18)
    password_reset_expire_minutes: int = 30
    # Asking again sooner than this does not send another email.
    password_reset_resend_seconds: int = 60
    # Where the web app runs; the emailed link is {frontend_url}/reset-password?token=...
    frontend_url: str = "http://localhost:5173"

    # ---- Employee data encrypted at rest (NFR-11, #18)
    # Fernet key(s), comma-separated; the first encrypts. Make one: python -m app.crypto
    # Empty = derived from JWT_SECRET (local development only).
    data_encryption_key: str = ""

    # ---- Email (app/notify.py). SMTP_HOST empty = emails are written to the log instead.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "PMS <no-reply@example.com>"
    smtp_tls: bool = True  # STARTTLS
    # ---- Alerts, refrigeration and scheduler (S2-4, S2-5, #13, #14)
    # Background loop that checks open doors, sends alert notifications and runs the daily
    # low-stock check. Alerts must reach staff within 60 s (NFR-2), so keep this at 30 s or less.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 10
    # Store time (HH:MM) of the daily projected low-stock check (FR-10).
    low_stock_check_time: str = "06:00"
    # A refrigeration door open longer than this raises an alarm (FR-16). Per-unit override
    # with PUT /api/refrigeration/units/{unitId}.
    door_open_limit_minutes: int = 5
    # Safe temperature range of a fridge in deg C; a reading outside it raises an alert.
    unit_temp_min_c: float = 0.0
    unit_temp_max_c: float = 8.0
    # Rule-based markdowns: max discount percent allowed by Manager rules (FR-14, TC-EXP-07).
    max_markdown_percent: float = 40.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
