from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    secret_key: str = "dev-secret-change-in-production"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/statement_recon"
    redis_url: str = "redis://localhost:6379/2"

    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    ai_max_tokens: int = 512

    field_encryption_key: str = ""

    sentry_dsn: str = ""

    # JWT
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Rate limiting
    rate_limit_per_minute: int = 100

    # Reconciliation matching
    # Amount tolerance (GBP) for treating two amounts as the same
    amount_tolerance_gbp: float = 0.01
    # Date tolerance (days) for matching invoices by date when reference differs
    date_tolerance_days: int = 7
    # Fuzzy match threshold for reference number matching (0–100)
    reference_fuzzy_threshold: int = 85


@lru_cache
def get_settings() -> Settings:
    return Settings()
