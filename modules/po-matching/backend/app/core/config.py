from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_env: str = "development"
    secret_key: str
    debug: bool = False

    # Database
    database_url: str
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AI
    anthropic_api_key: str
    ai_model: str = "claude-sonnet-4-6"
    ai_max_tokens: int = 4096

    # AWS
    aws_region: str = "eu-west-2"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket: str = "backbone-ai-documents"
    kms_key_id: str = ""

    # Encryption
    field_encryption_key: str  # base64-encoded 32-byte key

    # Auth
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # ERP OAuth apps (used only during connector registration)
    sage200_client_id: str = ""
    sage200_client_secret: str = ""
    sage200_redirect_uri: str = ""
    xero_client_id: str = ""
    xero_client_secret: str = ""
    xero_redirect_uri: str = ""

    # Rate limiting
    rate_limit_per_minute: int = 100
    api_rate_limit_per_minute: int = 1000

    # Alerting
    sentry_dsn: str = ""
    alert_from_email: str = "alerts@backbone-ai.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
