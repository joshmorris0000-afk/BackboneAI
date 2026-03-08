from typing import Optional
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)  # URL-safe identifier
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    config: Mapped["ClientConfig"] = relationship(back_populates="client", uselist=False)
    credentials: Mapped[list["ConnectorCredential"]] = relationship(back_populates="client")
    users: Mapped[list["User"]] = relationship(back_populates="client")


class ClientConfig(Base):
    """Per-client matching configuration. All values are operator-adjustable."""
    __tablename__ = "client_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), unique=True, nullable=False)

    # Matching tolerances
    price_tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.02"))
    qty_tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.00"))

    # Auto-approval
    auto_approve_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_approve_limit_gbp: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("5000.00"))
    auto_approve_requires_full_match: Mapped[bool] = mapped_column(Boolean, default=True)

    # AI extraction
    extraction_confidence_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.85"))

    # ERP
    erp_system: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # sage200 | xero | sap_b1
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    vat_registered: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_terms_default: Mapped[int] = mapped_column(default=30)

    # Alerts
    alert_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    alert_on_major_discrepancy: Mapped[bool] = mapped_column(Boolean, default=True)
    major_discrepancy_threshold_gbp: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("500.00"))

    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    client: Mapped["Client"] = relationship(back_populates="config")


class ConnectorCredential(Base):
    """
    Stores encrypted ERP/email credentials per client.

    Credentials are written ONCE during connector setup and then managed
    entirely by the system. Refresh tokens are rotated silently. Users
    are never prompted to re-authenticate during normal operation.

    All sensitive fields (tokens, passwords) are AES-256-GCM encrypted
    before being stored. The encryption key lives in AWS KMS.
    """
    __tablename__ = "connector_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(30), nullable=False)  # sage200 | xero | sap_b1 | imap | sage200_sql

    # OAuth fields (Sage 200 Cloud, Xero)
    access_token_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # encrypted
    refresh_token_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # encrypted
    token_expires_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)   # Xero tenant, Sage subscription ID

    # Generic key/value for non-OAuth connectors (SAP session, IMAP, SQL)
    host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    port: Mapped[Optional[int]] = mapped_column(nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # encrypted
    database_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    extra_config_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # encrypted JSON for any extras

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    client: Mapped["Client"] = relationship(back_populates="credentials")


from app.models.user import User  # noqa: E402
