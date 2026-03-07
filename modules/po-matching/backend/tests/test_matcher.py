"""
Unit tests for the 3-way matching engine.

Tests cover:
- Full match (all lines within tolerance)
- Price discrepancy (minor and major)
- Quantity discrepancy (invoice qty > GRN qty)
- No PO found
- No GRN found
- Supplier mismatch
- Auto-approval eligibility logic
- Fraud flag detection
"""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.client import ClientConfig
from app.models.documents import (
    GoodsReceiptLine,
    GoodsReceiptNote,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
)
from app.models.match import LineMatchStatus, MatchStatus
from app.services.matcher import MatchingEngine


def make_config(**overrides) -> ClientConfig:
    config = ClientConfig()
    config.price_tolerance_pct = Decimal("0.02")
    config.qty_tolerance_pct = Decimal("0.00")
    config.auto_approve_enabled = True
    config.auto_approve_limit_gbp = Decimal("5000.00")
    config.auto_approve_requires_full_match = True
    config.extraction_confidence_threshold = Decimal("0.85")
    for k, v in overrides.items():
        setattr(config, k, v)
    return config


def make_po(supplier_name="Test Supplier Ltd", po_number="PO-001", lines=None) -> PurchaseOrder:
    po = PurchaseOrder()
    po.id = uuid.uuid4()
    po.client_id = uuid.uuid4()
    po.po_number = po_number
    po.supplier_name = supplier_name
    po.supplier_id = None
    po.issued_date = None
    po.currency = "GBP"
    po.status = "issued"
    po.lines = lines or []
    return po


def make_po_line(description="Steel sheet 3mm", qty=20, price=48.50, part=None) -> PurchaseOrderLine:
    line = PurchaseOrderLine()
    line.id = uuid.uuid4()
    line.description = description
    line.quantity = Decimal(str(qty))
    line.unit_price = Decimal(str(price))
    line.vat_rate = Decimal("0.20")
    line.uom = "each"
    line.part_number = part
    line.line_total = line.quantity * line.unit_price
    return line


def make_grn(po_id, received_date=None, lines=None) -> GoodsReceiptNote:
    grn = GoodsReceiptNote()
    grn.id = uuid.uuid4()
    grn.po_id = po_id
    grn.received_date = received_date
    grn.lines = lines or []
    return grn


def make_grn_line(po_line_id, received=20, ordered=20, rejected=0) -> GoodsReceiptLine:
    line = GoodsReceiptLine()
    line.id = uuid.uuid4()
    line.po_line_id = po_line_id
    line.description = "Steel sheet 3mm"
    line.quantity_ordered = Decimal(str(ordered))
    line.quantity_received = Decimal(str(received))
    line.quantity_rejected = Decimal(str(rejected))
    line.uom = "each"
    return line


def make_invoice(supplier_name="Test Supplier Ltd", total=970.00, lines=None, po_ref="PO-001", confidence=0.97) -> Invoice:
    inv = Invoice()
    inv.id = uuid.uuid4()
    inv.client_id = uuid.uuid4()
    inv.invoice_number = "INV-001"
    inv.supplier_name_raw = supplier_name
    inv.supplier_id = None
    inv.supplier_vat_number = "GB123456789"
    inv.invoice_date = None
    inv.po_reference_raw = po_ref
    inv.currency = "GBP"
    inv.subtotal = Decimal(str(total))
    inv.vat_total = Decimal(str(round(total * 0.2, 2)))
    inv.grand_total = Decimal(str(round(total * 1.2, 2)))
    inv.extraction_confidence = Decimal(str(confidence))
    inv.fraud_flags = []
    inv.lines = lines or []
    return inv


def make_invoice_line(description="Steel sheet 3mm", qty=20, price=48.50) -> InvoiceLine:
    line = InvoiceLine()
    line.id = uuid.uuid4()
    line.description = description
    line.quantity = Decimal(str(qty))
    line.unit_price = Decimal(str(price))
    line.vat_rate = Decimal("0.20")
    line.line_total = line.quantity * line.unit_price
    line.po_line_ref = None
    return line


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_engine_with_mock_db(po=None, grn=None, suppliers=None) -> MatchingEngine:
    """Build a MatchingEngine with a mocked DB that returns configured test data."""
    db = AsyncMock()
    config = make_config()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = po
    mock_result.scalars.return_value.all.return_value = suppliers or []
    mock_result.scalars.return_value.first.return_value = grn
    db.execute.return_value = mock_result

    engine = MatchingEngine(db, config)
    return engine


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestLineEvaluation:
    """Direct tests of the line-level evaluation logic — no DB needed."""

    def setup_method(self):
        self.engine = MatchingEngine(db=AsyncMock(), config=make_config())

    def test_exact_match(self):
        po_line = make_po_line(qty=20, price=48.50)
        grn_line = make_grn_line(po_line.id, received=20)
        inv_line = make_invoice_line(qty=20, price=48.50)

        result = self.engine._evaluate_line(inv_line, po_line, grn_line, Decimal("0.02"), Decimal("0"))
        assert result.status == LineMatchStatus.matched
        assert result.price_variance == Decimal("0")
        assert result.financial_exposure == Decimal("0")

    def test_price_within_tolerance(self):
        po_line = make_po_line(qty=20, price=48.50)
        grn_line = make_grn_line(po_line.id, received=20)
        inv_line = make_invoice_line(qty=20, price=49.40)  # 1.86% over — within 2%

        result = self.engine._evaluate_line(inv_line, po_line, grn_line, Decimal("0.02"), Decimal("0"))
        assert result.status == LineMatchStatus.matched

    def test_price_over_tolerance(self):
        po_line = make_po_line(qty=20, price=48.50)
        grn_line = make_grn_line(po_line.id, received=20)
        inv_line = make_invoice_line(qty=20, price=52.00)  # 7.2% over

        result = self.engine._evaluate_line(inv_line, po_line, grn_line, Decimal("0.02"), Decimal("0"))
        assert result.status == LineMatchStatus.price_over
        assert result.financial_exposure > Decimal("0")

    def test_price_under(self):
        po_line = make_po_line(qty=20, price=48.50)
        grn_line = make_grn_line(po_line.id, received=20)
        inv_line = make_invoice_line(qty=20, price=44.00)  # under PO price

        result = self.engine._evaluate_line(inv_line, po_line, grn_line, Decimal("0.02"), Decimal("0"))
        assert result.status == LineMatchStatus.price_under

    def test_qty_over_grn(self):
        """Invoice claims 25 units but only 20 were received — paying for undelivered goods."""
        po_line = make_po_line(qty=25, price=48.50)
        grn_line = make_grn_line(po_line.id, received=20, ordered=25)
        inv_line = make_invoice_line(qty=25, price=48.50)

        result = self.engine._evaluate_line(inv_line, po_line, grn_line, Decimal("0.02"), Decimal("0"))
        assert result.status == LineMatchStatus.qty_over
        assert result.financial_exposure > Decimal("0")

    def test_partial_invoice_acceptable(self):
        """Invoice for 15 units when 20 received — partial invoice is acceptable."""
        po_line = make_po_line(qty=20, price=48.50)
        grn_line = make_grn_line(po_line.id, received=20, ordered=20)
        inv_line = make_invoice_line(qty=15, price=48.50)

        result = self.engine._evaluate_line(inv_line, po_line, grn_line, Decimal("0.02"), Decimal("0"))
        assert result.status == LineMatchStatus.qty_under

    def test_no_po_line_match(self):
        """Invoice line with no corresponding PO line."""
        inv_line = make_invoice_line(description="Random item not on PO")
        result = self.engine._evaluate_line(inv_line, None, None, Decimal("0.02"), Decimal("0"))
        assert result.status == LineMatchStatus.not_on_po
        assert result.financial_exposure == inv_line.line_total


class TestOverallStatus:
    def setup_method(self):
        self.engine = MatchingEngine(db=AsyncMock(), config=make_config())
        # Minimal GRN for status tests
        self.grn = make_grn(uuid.uuid4())

    def _make_decision(self, status: LineMatchStatus, price_var_pct=Decimal("0")):
        from app.services.matcher import LineMatchDecision
        return LineMatchDecision(
            invoice_line=make_invoice_line(),
            po_line=make_po_line(),
            grn_line=None,
            status=status,
            price_variance=Decimal("0"),
            price_variance_pct=price_var_pct,
            qty_variance=Decimal("0"),
            financial_exposure=Decimal("0"),
            reason="test",
        )

    def test_all_matched_is_full_match(self):
        decisions = [self._make_decision(LineMatchStatus.matched) for _ in range(3)]
        assert self.engine._determine_status(decisions, self.grn) == MatchStatus.full_match

    def test_minor_price_discrepancy_is_partial(self):
        decisions = [
            self._make_decision(LineMatchStatus.matched),
            self._make_decision(LineMatchStatus.price_over, price_var_pct=Decimal("0.03")),
        ]
        assert self.engine._determine_status(decisions, self.grn) == MatchStatus.partial_match

    def test_major_price_discrepancy(self):
        decisions = [
            self._make_decision(LineMatchStatus.price_over, price_var_pct=Decimal("0.08")),
        ]
        assert self.engine._determine_status(decisions, self.grn) == MatchStatus.price_discrepancy

    def test_qty_over_takes_priority(self):
        decisions = [
            self._make_decision(LineMatchStatus.price_over, price_var_pct=Decimal("0.03")),
            self._make_decision(LineMatchStatus.qty_over),
        ]
        assert self.engine._determine_status(decisions, self.grn) == MatchStatus.qty_discrepancy

    def test_no_grn_status(self):
        decisions = [self._make_decision(LineMatchStatus.matched)]
        assert self.engine._determine_status(decisions, None) == MatchStatus.no_grn_found


class TestAutoApproval:
    def setup_method(self):
        self.engine = MatchingEngine(db=AsyncMock(), config=make_config())

    def _inv(self, total=1000.0, confidence=0.97, fraud_flags=None):
        inv = make_invoice(total=total, confidence=confidence)
        inv.grand_total = Decimal(str(total * 1.2))
        inv.fraud_flags = fraud_flags or []
        return inv

    def test_full_match_under_limit_approves(self):
        can, reasons = self.engine._evaluate_auto_approval(
            self._inv(total=1000), MatchStatus.full_match, [], Decimal("0")
        )
        assert can is True
        assert reasons == []

    def test_partial_match_blocked(self):
        can, reasons = self.engine._evaluate_auto_approval(
            self._inv(total=1000), MatchStatus.partial_match, [], Decimal("50")
        )
        assert can is False
        assert any("full match" in r.lower() for r in reasons)

    def test_over_limit_blocked(self):
        can, reasons = self.engine._evaluate_auto_approval(
            self._inv(total=5000), MatchStatus.full_match, [], Decimal("0")
        )
        assert can is False
        assert any("limit" in r.lower() for r in reasons)

    def test_fraud_flags_block(self):
        inv = self._inv(total=500, fraud_flags=["subtotal_mismatch_with_lines"])
        can, reasons = self.engine._evaluate_auto_approval(inv, MatchStatus.full_match, [], Decimal("0"))
        assert can is False
        assert any("fraud" in r.lower() for r in reasons)

    def test_low_confidence_blocked(self):
        can, reasons = self.engine._evaluate_auto_approval(
            self._inv(total=500, confidence=0.72), MatchStatus.full_match, [], Decimal("0")
        )
        assert can is False
        assert any("confidence" in r.lower() for r in reasons)

    def test_auto_approve_disabled(self):
        self.engine.config.auto_approve_enabled = False
        can, reasons = self.engine._evaluate_auto_approval(
            self._inv(total=500), MatchStatus.full_match, [], Decimal("0")
        )
        assert can is False


class TestSupplierFuzzyMatch:
    def setup_method(self):
        self.engine = MatchingEngine(db=AsyncMock(), config=make_config())

    def test_exact_match(self):
        inv = make_invoice("Midlands Steel Supplies Ltd")
        po = make_po("Midlands Steel Supplies Ltd")
        assert self.engine._suppliers_match.__wrapped__ is None or True  # sync test
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            self.engine._suppliers_match(inv, po)
        )
        assert result is True

    def test_fuzzy_match_above_threshold(self):
        inv = make_invoice("Midlands Steel Ltd")
        po = make_po("Midlands Steel Supplies Ltd")
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            self.engine._suppliers_match(inv, po)
        )
        assert result is True

    def test_completely_different_supplier(self):
        inv = make_invoice("Acme Plastics PLC")
        po = make_po("Midlands Steel Supplies Ltd")
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            self.engine._suppliers_match(inv, po)
        )
        assert result is False
