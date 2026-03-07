from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    secret_key: str = "dev-secret"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/price_drift"
    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    ai_max_tokens: int = 512

    field_encryption_key: str = ""

    sentry_dsn: str = ""
    alert_from_email: str = "alerts@backbone-ai.com"

    # Drift defaults (overridden per client in DB)
    default_drift_tolerance_pct: float = 0.02   # 2%
    warning_threshold_pct: float = 0.02         # 2%
    alert_threshold_pct: float = 0.05           # 5%
    critical_threshold_pct: float = 0.10        # 10%


@lru_cache
def get_settings() -> Settings:
    return Settings()
