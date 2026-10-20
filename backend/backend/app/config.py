from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://pms_user:pms_password@localhost:5432/pms_db"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
