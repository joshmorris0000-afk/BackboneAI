import uuid
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MatchStatus(str, Enum):
    full_match = "full_match"
    partial_match = "partial_match"
    price_discrepancy = "price_discrepancy"
    qty_discrepancy = "qty_discrepancy"
    supplier_mismatch = "supplier_mismatch"
    no_po_found = "no_po_found"
    no_grn_found = "no_grn_found"
    manual_override = "manual_override"


class LineMatchStatus(str, Enum):
    matched = "matched"
    price_over = "price_over"
    price_under = "price_under"
    qty_over = "qty_over"
    qty_under = "qty_under"
    not_on_po = "not_on_po"
    not_received = "not_received"


class MatchedBy(str, Enum):
    auto = "auto"
    manual = "manual"


class MatchResult(Base):
    __tablename__ = "match_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    po_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=True)
    grn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("goods_receipt_notes.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    match_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"), nullable=False)
    matched_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    matched_by: Mapped[str] = mapped_column(String(10), default=MatchedBy.auto, nullable=False)

    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    exception_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    discrepancy_total: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"), nullable=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="match_results")
    purchase_order: Mapped["PurchaseOrder | None"] = relationship(back_populates="match_results")
    grn: Mapped["GoodsReceiptNote | None"] = relationship(back_populates="match_results")
    line_results: Mapped[list["MatchLineResult"]] = relationship(back_populates="match_result", cascade="all, delete-orphan")


class MatchLineResult(Base):
    __tablename__ = "match_line_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("match_results.id"), nullable=False)
    invoice_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoice_lines.id"), nullable=False)
    po_line_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_order_lines.id"), nullable=True)
    grn_line_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("goods_receipt_lines.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False)

    po_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    invoice_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    price_variance: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"), nullable=False)
    price_variance_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=Decimal("0"), nullable=False)

    po_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    grn_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    invoice_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    qty_variance: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"), nullable=False)

    financial_exposure: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"), nullable=False)

    match_result: Mapped["MatchResult"] = relationship(back_populates="line_results")
    invoice_line: Mapped["InvoiceLine"] = relationship(back_populates="match_line_results")
    po_line: Mapped["PurchaseOrderLine | None"] = relationship(back_populates="match_line_results")
    grn_line: Mapped["GoodsReceiptLine | None"] = relationship(back_populates="match_line_results")


# Deferred imports
from app.models.documents import GoodsReceiptLine, GoodsReceiptNote, Invoice, InvoiceLine, PurchaseOrder, PurchaseOrderLine  # noqa: E402
from app.models.user import User  # noqa: E402
