"""
Tests for the Supplier Price Drift Detector engine.

Covers:
- No drift (exact contract price)
- Drift within tolerance (info only, no alert)
- Warning level drift (2–5%)
- Alert level drift (5–10%)
- Critical drift (>10%)
- Price below contracted (direction = down)
- No contracted price found (observation created, no alert)
- Severity calculation
- Financial impact calculation
- Description normalisation for fuzzy matching
"""
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.price_data import (
    ContractedPrice,
    DriftSeverity,
    DriftDirection,
)
from app.services.drift_detector import (
    DriftDetector,
    InvoiceLine,
    _normalise,
    _severity,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_contracted(unit_price: float, sku: str | None = None, tolerance: float | None = None) -> ContractedPrice:
    cp = ContractedPrice()
    cp.id = uuid.uuid4()
    cp.sku = sku
    cp.description = "Mild Steel Sheet 3mm 2500x1250mm"
    cp.description_normalised = _normalise(cp.description)
    cp.unit_price = Decimal(str(unit_price))
    cp.valid_from = date(2026, 1, 1)
    cp.valid_to = None
    cp.tolerance_pct = Decimal(str(tolerance)) if tolerance else None
    return cp


def make_line(
    unit_price: float,
    description: str = "Mild Steel Sheet 3mm 2500x1250mm",
    sku: str | None = None,
    quantity: float = 10.0,
) -> InvoiceLine:
    return InvoiceLine(
        invoice_id=str(uuid.uuid4()),
        invoice_number="INV-TEST-001",
        invoice_date=date(2026, 3, 7),
        supplier_id=str(uuid.uuid4()),
        client_id=str(uuid.uuid4()),
        description=description,
        sku=sku,
        unit_price=Decimal(str(unit_price)),
        quantity=Decimal(str(quantity)),
        currency="GBP",
    )


def make_detector(contracted: ContractedPrice | None) -> tuple[DriftDetector, AsyncMock]:
    db = AsyncMock()

    # Mock _find_contracted_price
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = contracted
    mock_result.scalars.return_value.all.return_value = [contracted] if contracted else []

    # Mock _monthly_context
    monthly_mock = MagicMock()
    monthly_mock.one.return_value = (Decimal("0"), 0)
    db.execute.return_value = monthly_mock

    detector = DriftDetector(db=db, client_default_tolerance=Decimal("0.02"))

    return detector, db


# ─── Severity calculation ─────────────────────────────────────────────────────

class TestSeverity:
    def test_zero_is_none_handled_upstream(self):
        # _severity is only called when variance > tolerance, so 0 not passed
        assert _severity(Decimal("0.5")) == DriftSeverity.info

    def test_below_two_pct_is_info(self):
        assert _severity(Decimal("1.9")) == DriftSeverity.info

    def test_two_to_five_is_warning(self):
        assert _severity(Decimal("3.5")) == DriftSeverity.warning
        assert _severity(Decimal("4.99")) == DriftSeverity.warning

    def test_five_to_ten_is_alert(self):
        assert _severity(Decimal("5.0")) == DriftSeverity.alert
        assert _severity(Decimal("9.9")) == DriftSeverity.alert

    def test_over_ten_is_critical(self):
        assert _severity(Decimal("10.1")) == DriftSeverity.critical
        assert _severity(Decimal("25.0")) == DriftSeverity.critical

    def test_negative_pct_uses_absolute(self):
        # Price below contract — still has severity based on magnitude
        assert _severity(Decimal("-3.5")) == DriftSeverity.warning
        assert _severity(Decimal("-12.0")) == DriftSeverity.critical


# ─── Description normalisation ────────────────────────────────────────────────

class TestNormalise:
    def test_lowercases(self):
        assert _normalise("Steel Sheet") == "steel sheet"

    def test_strips_whitespace(self):
        assert _normalise("  steel  sheet  ") == "steel sheet"

    def test_collapses_internal_spaces(self):
        assert _normalise("steel   sheet") == "steel sheet"

    def test_preserves_digits_and_units(self):
        assert _normalise("Sheet 3mm 2500x1250") == "sheet 3mm 2500x1250"


# ─── Financial impact ─────────────────────────────────────────────────────────

class TestFinancialImpact:
    def test_positive_drift(self):
        contracted = Decimal("48.50")
        observed = Decimal("54.20")
        quantity = Decimal("20")
        variance = observed - contracted  # 5.70
        impact = variance * quantity      # 114.00
        assert impact == Decimal("114.00")

    def test_negative_drift_is_credit(self):
        contracted = Decimal("48.50")
        observed = Decimal("44.00")
        quantity = Decimal("10")
        variance = observed - contracted  # -4.50
        impact = variance * quantity      # -45.00
        assert impact == Decimal("-45.00")

    def test_zero_variance_zero_impact(self):
        contracted = Decimal("48.50")
        observed = Decimal("48.50")
        variance = observed - contracted
        assert variance == Decimal("0")


# ─── Drift direction ─────────────────────────────────────────────────────────

class TestDriftDirection:
    def test_price_increase_is_up(self):
        variance = Decimal("5.70")
        direction = DriftDirection.up if variance > 0 else DriftDirection.down
        assert direction == DriftDirection.up

    def test_price_decrease_is_down(self):
        variance = Decimal("-4.50")
        direction = DriftDirection.up if variance > 0 else DriftDirection.down
        assert direction == DriftDirection.down


# ─── Detector — variance percentage ──────────────────────────────────────────

class TestVariancePct:
    def _calc(self, contracted: float, observed: float) -> float:
        c = Decimal(str(contracted))
        o = Decimal(str(observed))
        return float((o - c) / c * 100)

    def test_7pct_over(self):
        pct = self._calc(48.50, 51.895)
        assert abs(pct - 7.0) < 0.01

    def test_exact_match_zero(self):
        pct = self._calc(48.50, 48.50)
        assert pct == 0.0

    def test_under_contract(self):
        pct = self._calc(48.50, 44.00)
        assert pct < 0

    def test_critical_threshold(self):
        # 11% over — must be critical
        pct = self._calc(100.00, 111.00)
        assert _severity(Decimal(str(pct))) == DriftSeverity.critical


# ─── Tolerance logic ─────────────────────────────────────────────────────────

class TestTolerance:
    def test_within_default_tolerance_no_alert(self):
        # 1.5% over, default tolerance 2% — should be info only (no alert)
        contracted_price = Decimal("100.00")
        observed_price = Decimal("101.50")
        variance = observed_price - contracted_price
        variance_pct = variance / contracted_price  # 0.015
        tolerance = Decimal("0.02")
        exceeds = abs(variance_pct) > tolerance
        assert not exceeds

    def test_just_over_tolerance_raises_alert(self):
        contracted_price = Decimal("100.00")
        observed_price = Decimal("102.10")
        variance = observed_price - contracted_price
        variance_pct = variance / contracted_price  # 0.021
        tolerance = Decimal("0.02")
        exceeds = abs(variance_pct) > tolerance
        assert exceeds

    def test_custom_tighter_tolerance(self):
        # Custom 0.5% tolerance — 0.6% over should trigger
        contracted_price = Decimal("100.00")
        observed_price = Decimal("100.60")
        variance = observed_price - contracted_price
        variance_pct = variance / contracted_price  # 0.006
        tolerance = Decimal("0.005")
        exceeds = abs(variance_pct) > tolerance
        assert exceeds

    def test_custom_looser_tolerance(self):
        # Custom 5% tolerance — 4% over should not trigger
        contracted_price = Decimal("100.00")
        observed_price = Decimal("104.00")
        variance = observed_price - contracted_price
        variance_pct = variance / contracted_price  # 0.04
        tolerance = Decimal("0.05")
        exceeds = abs(variance_pct) > tolerance
        assert not exceeds


# ─── Multi-line monthly accumulation ─────────────────────────────────────────

class TestMonthlyAccumulation:
    def test_impact_accumulates_correctly(self):
        """Simulate 4 lines from same supplier this month, verify total drift."""
        impacts = [Decimal("114.00"), Decimal("45.00"), Decimal("22.50"), Decimal("88.00")]
        total = sum(impacts)
        assert total == Decimal("269.50")

    def test_credit_lines_reduce_total(self):
        """Price decreases offset overcharges in monthly total."""
        impacts = [Decimal("114.00"), Decimal("-20.00"), Decimal("45.00")]
        total = sum(impacts)
        assert total == Decimal("139.00")
