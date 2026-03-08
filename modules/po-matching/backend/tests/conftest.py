"""
pytest configuration for the PO Matching backend.

Sets required environment variables BEFORE any application module is imported,
so that pydantic-settings can build the Settings object without an .env file
or real credentials.
"""
import os

# Set all required env vars before any app code is imported.
# These are dummy values — the tests mock all external dependencies.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_po_matching")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcy0h")
