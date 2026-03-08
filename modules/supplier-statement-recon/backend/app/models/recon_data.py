"""
Data models for Supplier Statement Reconciliation.

Reconciliation compares two views of the same transactions:
  - The supplier's statement: what they say you owe them
  - Your ledger: what you have recorded as owing

Discrepancies (items on one side with no match on the other) need investigation.
"""
import uuid
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReconciliationStatus(str, Enum):
    pending = "pending"           # just created, not yet run
    in_progress = "in_progress"   # matching engine running
    completed = "completed"       # matching complete, awaiting human review
    reviewed = "reviewed"         # human has reviewed all discrepancies
    closed = "closed"             # fully resolved / filed


class MatchStatus(str, Enum):
    matched = "matched"           # statement line matches ledger line exactly
    amount_mismatch = "amount_mismatch"   # found a candidate but amounts differ
    date_mismatch = "date_mismatch"       # found a candidate but dates differ
    on_statement_only = "on_statement_only"   # supplier claims this; we have no record
    on_ledger_only = "on_ledger_only"         # we have it; supplier doesn't show it
    disputed = "disputed"         # raised as formal dispute with supplier
    resolved = "resolved"         # discrepancy explained and closed


class DiscrepancyType(str, Enum):
    missing_from_ledger = "missing_from_ledger"   # on statement, not in our books
    missing_from_statement = "missing_from_statement"   # in our books, not on statement
    amount_difference = "amount_difference"       # both sides have it but amounts differ
    date_difference = "date_difference"           # amounts match, dates don't
    duplicate_on_statement = "duplicate_on_statement"   # supplier listed same invoice twice
    credit_not_applied = "credit_not_applied"     # credit note we issued not on statement


# ─── Reconciliation Session ────────────────────────────────────────────────────

class ReconSession(Base):
    """
    One reconciliation run for a supplier in a given period.
    Typically created when the supplier sends their monthly statement.
    """
    __tablename__ = "recon_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False, index=True)

    statement_date: Mapped[Date] = mapped_column(Date, nullable=False)
    period_from: Mapped[Date] = mapped_column(Date, nullable=False)
    period_to: Mapped[Date] = mapped_column(Date, nullable=False)

    # Statement totals as per supplier
    statement_total: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    statement_currency: Mapped[str] = mapped_column(String(3), default="GBP", nullable=False)

    # Ledger totals for the same period
    ledger_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Variance: statement_total - ledger_total (positive = supplier overstates our balance)
    variance: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    status: Mapped[str] = mapped_column(String(15), default=ReconciliationStatus.pending.value, nullable=False, index=True)

    # Counts updated after matching
    matched_count: Mapped[int] = mapped_column(default=0)
    discrepancy_count: Mapped[int] = mapped_column(default=0)
    total_discrepancy_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # AI-generated executive summary written after matching completes
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Source: how the statement arrived (manual_upload | email | edi)
    source: Mapped[str] = mapped_column(String(20), default="manual_upload", nullable=False)
    raw_statement_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # original text before parsing

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    statement_lines: Mapped[List["StatementLine"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    ledger_lines: Mapped[List["LedgerLine"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    discrepancies: Mapped[List["ReconDiscrepancy"]] = relationship(back_populates="session", cascade="all, delete-orphan")


# ─── Statement Line ────────────────────────────────────────────────────────────

class StatementLine(Base):
    """
    A single line from the supplier's statement.
    Parsed from PDF/CSV/email by Claude or entered manually.
    """
    __tablename__ = "statement_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recon_sessions.id"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False)

    # As stated by the supplier
    supplier_reference: Mapped[str] = mapped_column(String(100), nullable=False)  # their invoice/credit note ref
    our_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # our PO/invoice ref if shown
    transaction_date: Mapped[Date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)  # positive=invoice, negative=credit
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(20), default="invoice", nullable=False)  # invoice | credit_note | payment

    # Set by reconciliation engine
    match_status: Mapped[str] = mapped_column(String(25), default=MatchStatus.on_statement_only.value, nullable=False, index=True)
    matched_ledger_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("ledger_lines.id"), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["ReconSession"] = relationship(back_populates="statement_lines")
    matched_ledger_line: Mapped[Optional["LedgerLine"]] = relationship(foreign_keys=[matched_ledger_line_id])


# ─── Ledger Line ──────────────────────────────────────────────────────────────

class LedgerLine(Base):
    """
    A transaction from the client's own AP ledger for this supplier and period.
    Pulled from the ERP (Sage 200, Xero, etc.) via the connector.
    """
    __tablename__ = "ledger_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recon_sessions.id"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False)

    # From our ERP
    our_reference: Mapped[str] = mapped_column(String(100), nullable=False)  # our invoice/PO ref
    supplier_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # supplier's ref if captured
    transaction_date: Mapped[Date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(20), default="invoice", nullable=False)
    erp_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # ID in source ERP

    # Set by reconciliation engine
    match_status: Mapped[str] = mapped_column(String(25), default=MatchStatus.on_ledger_only.value, nullable=False, index=True)
    matched_statement_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("statement_lines.id"), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["ReconSession"] = relationship(back_populates="ledger_lines")
    matched_statement_line: Mapped[Optional["StatementLine"]] = relationship(foreign_keys=[matched_statement_line_id])


# ─── Discrepancy ──────────────────────────────────────────────────────────────

class ReconDiscrepancy(Base):
    """
    A discrepancy identified during reconciliation that requires human attention.
    One record per unresolved issue.
    """
    __tablename__ = "recon_discrepancies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recon_sessions.id"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False)

    discrepancy_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(15), default=MatchStatus.on_statement_only.value, nullable=False)

    # Which lines are involved (one or both may be set)
    statement_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("statement_lines.id"), nullable=True)
    ledger_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("ledger_lines.id"), nullable=True)

    # Financial impact of this discrepancy
    financial_impact: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    # AI-generated plain-English explanation
    ai_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Human resolution
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    session: Mapped["ReconSession"] = relationship(back_populates="discrepancies")
    statement_line: Mapped[Optional["StatementLine"]] = relationship(foreign_keys=[statement_line_id])
    ledger_line: Mapped[Optional["LedgerLine"]] = relationship(foreign_keys=[ledger_line_id])
