"""
Data models for the Supplier Price Drift Detector.

Tracks:
- Contracted prices (from supplier agreements / price lists)
- Observed prices (from invoices as they are processed)
- Drift alerts (when observed price deviates from contracted price beyond threshold)
"""
import uuid
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DriftSeverity(str, Enum):
    info = "info"           # 0–2%: within typical tolerance, logged only
    warning = "warning"     # 2–5%: monitor — may be legitimate (spot price, surcharge)
    alert = "alert"         # 5–10%: likely unauthorised drift — human review required
    critical = "critical"   # >10%: significant overcharge — immediate escalation


class DriftDirection(str, Enum):
    up = "up"       # price increased above contract
    down = "down"   # price decreased (usually fine, but track it)


class AlertStatus(str, Enum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"
    disputed = "disputed"


# ─── Contracted Price ─────────────────────────────────────────────────────────

class ContractedPrice(Base):
    """
    The agreed price for a product/SKU from a specific supplier.
    Source: manually entered, or imported from supplier contract document.
    """
    __tablename__ = "contracted_prices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False, index=True)

    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    description_normalised: Mapped[str] = mapped_column(Text, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="GBP", nullable=False)
    uom: Mapped[str] = mapped_column(String(20), default="each", nullable=False)

    valid_from: Mapped[Date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)

    # Allowable variance before alert is raised (overrides client default if set)
    tolerance_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    observations: Mapped[List["PriceObservation"]] = relationship(back_populates="contracted_price")


# ─── Price Observation ────────────────────────────────────────────────────────

class PriceObservation(Base):
    """
    A price actually observed on a supplier invoice for a matched SKU/product.
    Created automatically when an invoice is processed through the system.
    """
    __tablename__ = "price_observations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False, index=True)
    contracted_price_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("contracted_prices.id"), nullable=True)

    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_date: Mapped[Date] = mapped_column(Date, nullable=False)

    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description_raw: Mapped[str] = mapped_column(Text, nullable=False)
    observed_unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="GBP", nullable=False)

    # Drift fields (null if no contracted price found)
    contracted_unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    price_variance: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    price_variance_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4), nullable=True)
    financial_impact: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)

    drift_severity: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    drift_direction: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contracted_price: Mapped[Optional["ContractedPrice"]] = relationship(back_populates="observations")
    alert: Mapped[Optional["DriftAlert"]] = relationship(back_populates="observation", uselist=False)


# ─── Drift Alert ──────────────────────────────────────────────────────────────

class DriftAlert(Base):
    """
    Raised when a price observation exceeds the configured drift threshold.
    Tracks the full lifecycle: open → acknowledged → resolved/disputed.
    """
    __tablename__ = "drift_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False, index=True)
    observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("price_observations.id"), nullable=False, unique=True)

    severity: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(5), nullable=False)
    status: Mapped[str] = mapped_column(String(15), default=AlertStatus.open.value, nullable=False, index=True)

    total_drift_this_month: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    occurrences_this_month: Mapped[int] = mapped_column(default=1)

    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    observation: Mapped["PriceObservation"] = relationship(back_populates="alert")


# ─── Supplier Price Trend ─────────────────────────────────────────────────────

class SupplierPriceTrend(Base):
    """
    Monthly rollup: total drift by supplier, used for trend analysis and reporting.
    Populated by a nightly aggregation job.
    """
    __tablename__ = "supplier_price_trends"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False)

    year: Mapped[int] = mapped_column(nullable=False)
    month: Mapped[int] = mapped_column(nullable=False)

    total_invoiced: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    total_contracted: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    total_drift: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    drift_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=Decimal("0"))
    observation_count: Mapped[int] = mapped_column(default=0)
    alert_count: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
