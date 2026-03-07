from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    secret_key: str = "dev-secret-change-in-production"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/price_drift"
    redis_url: str = "redis://localhost:6379/1"

    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    ai_max_tokens: int = 200

    field_encryption_key: str = ""  # base64-encoded 32-byte AES key

    sentry_dsn: str = ""

    # JWT
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Rate limiting (requests per minute per IP)
    rate_limit_per_minute: int = 100

    # Drift detection thresholds
    default_drift_tolerance_pct: float = 0.02   # 2%
    warning_threshold_pct: float = 0.02         # 2%
    alert_threshold_pct: float = 0.05           # 5%
    critical_threshold_pct: float = 0.10        # 10%

    # Email alerts (SMTP)
    alert_from_email: str = "alerts@backbone-ai.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""

    # Minimum severity that triggers an email notification
    # Values: warning | alert | critical
    email_notification_threshold: str = "alert"


@lru_cache
def get_settings() -> Settings:
    return Settings()
