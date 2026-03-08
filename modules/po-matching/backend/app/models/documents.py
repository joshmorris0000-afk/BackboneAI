"""
Core financial document models: Purchase Orders, Goods Receipts, Invoices.
"""
from typing import Optional
import uuid
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class POStatus(str, Enum):
    draft = "draft"
    issued = "issued"
    partially_received = "partially_received"
    fully_received = "fully_received"
    cancelled = "cancelled"


class InvoiceStatus(str, Enum):
    pending_extraction = "pending_extraction"
    extracted = "extracted"
    matched = "matched"
    exception = "exception"
    approved = "approved"
    paid = "paid"


class DocumentSource(str, Enum):
    sage200 = "sage200"
    xero = "xero"
    sap_b1 = "sap_b1"
    manual = "manual"
    csv_import = "csv_import"
    email = "email"
    api = "api"


# ─── Purchase Order ────────────────────────────────────────────────────────────

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    po_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issued_date: Mapped[Date] = mapped_column(Date, nullable=False)
    expected_delivery: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="GBP", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=POStatus.issued, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # ERP internal ID
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    lines: Mapped[list["PurchaseOrderLine"]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan")
    match_results: Mapped[list["MatchResult"]] = relationship(back_populates="purchase_order")


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    part_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.20"), nullable=False)
    uom: Mapped[str] = mapped_column(String(20), default="each", nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="lines")
    grn_lines: Mapped[list["GoodsReceiptLine"]] = relationship(back_populates="po_line")
    match_line_results: Mapped[list["MatchLineResult"]] = relationship(back_populates="po_line")


# ─── Goods Receipt ─────────────────────────────────────────────────────────────

class GoodsReceiptNote(Base):
    __tablename__ = "goods_receipt_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    grn_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    po_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=True)
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    received_date: Mapped[Date] = mapped_column(Date, nullable=False)
    received_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["GoodsReceiptLine"]] = relationship(back_populates="grn", cascade="all, delete-orphan")
    match_results: Mapped[list["MatchResult"]] = relationship(back_populates="grn")


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("goods_receipt_notes.id"), nullable=False)
    po_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_order_lines.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    part_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    quantity_rejected: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"), nullable=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uom: Mapped[str] = mapped_column(String(20), default="each", nullable=False)

    grn: Mapped["GoodsReceiptNote"] = relationship(back_populates="lines")
    po_line: Mapped[Optional["PurchaseOrderLine"]] = relationship(back_populates="grn_lines")
    match_line_results: Mapped[list["MatchLineResult"]] = relationship(back_populates="grn_line")


# ─── Invoice ───────────────────────────────────────────────────────────────────

class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    supplier_name_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_vat_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    invoice_date: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)
    po_reference_raw: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="GBP", nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    vat_total: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"), nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # encrypted S3 key
    extraction_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    extraction_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    extraction_raw: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # full AI response
    fraud_flags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=InvoiceStatus.pending_extraction, nullable=False, index=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    lines: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    match_results: Mapped[list["MatchResult"]] = relationship(back_populates="invoice")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.20"), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    po_line_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    invoice: Mapped["Invoice"] = relationship(back_populates="lines")
    match_line_results: Mapped[list["MatchLineResult"]] = relationship(back_populates="invoice_line")


# ─── Deferred imports (avoid circular) ────────────────────────────────────────
from app.models.match import MatchLineResult, MatchResult  # noqa: E402
