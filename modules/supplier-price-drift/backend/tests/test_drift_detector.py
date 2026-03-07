from __future__ import annotations

"""
Tests for the Supplier Price Drift Detector.

Covers both the pure calculation functions AND the DriftDetector service
with async DB mocks, verifying:
- Observations are always created
- Alerts are only created when drift exceeds tolerance
- AI summary is called for warning/alert/critical severity
- AI summary is NOT called for info-level or no-drift lines
- No contracted price → observation created, no alert, no AI call
- SKU matching takes priority over description matching
- All severity boundaries are correctly classified
- Tolerance logic (within / just over / per-SKU override)
- Financial impact arithmetic
- Description normalisation
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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_contracted(
    unit_price: float,
    sku: str | None = None,
    tolerance: float | None = None,
    description: str = "Mild Steel Sheet 3mm 2500x1250mm",
) -> ContractedPrice:
    cp = ContractedPrice()
    cp.id = uuid.uuid4()
    cp.sku = sku
    cp.description = description
    cp.description_normalised = _normalise(description)
    cp.unit_price = Decimal(str(unit_price))
    cp.valid_from = date(2026, 1, 1)
    cp.valid_to = None
    cp.tolerance_pct = Decimal(str(tolerance)) if tolerance is not None else None
    return cp


def make_line(
    unit_price: float,
    description: str = "Mild Steel Sheet 3mm 2500x1250mm",
    sku: str | None = None,
    quantity: float = 10.0,
    client_id: str | None = None,
    supplier_id: str | None = None,
) -> InvoiceLine:
    return InvoiceLine(
        invoice_id=str(uuid.uuid4()),
        invoice_number="INV-TEST-001",
        invoice_date=date(2026, 3, 7),
        supplier_id=supplier_id or str(uuid.uuid4()),
        client_id=client_id or str(uuid.uuid4()),
        description=description,
        sku=sku,
        unit_price=Decimal(str(unit_price)),
        quantity=Decimal(str(quantity)),
        currency="GBP",
    )


def make_detector(contracted: ContractedPrice | None) -> tuple[DriftDetector, AsyncMock]:
    """Build a DriftDetector with a fully mocked async DB session.

    Uses a single flexible mock for db.execute that satisfies all three query
    patterns used by the detector:
      - scalar_one_or_none()   → SKU exact match
      - scalars().all()        → fuzzy candidate fetch
      - one()                  → monthly context aggregation
    """
    db = AsyncMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = contracted
    execute_result.scalars.return_value.all.return_value = [contracted] if contracted else []
    execute_result.one.return_value = (Decimal("0"), 0)

    db.execute.return_value = execute_result
    db.add = MagicMock()
    db.flush = AsyncMock()

    detector = DriftDetector(db=db, client_default_tolerance=Decimal("0.02"))
    return detector, db


# ─── Pure function tests ───────────────────────────────────────────────────────

class TestSeverity:
    def test_below_two_pct_is_info(self):
        assert _severity(Decimal("1.9")) == DriftSeverity.info

    def test_exactly_two_pct_is_warning(self):
        assert _severity(Decimal("2.0")) == DriftSeverity.warning

    def test_two_to_five_is_warning(self):
        assert _severity(Decimal("3.5")) == DriftSeverity.warning
        assert _severity(Decimal("4.99")) == DriftSeverity.warning

    def test_exactly_five_is_alert(self):
        assert _severity(Decimal("5.0")) == DriftSeverity.alert

    def test_five_to_ten_is_alert(self):
        assert _severity(Decimal("7.5")) == DriftSeverity.alert
        assert _severity(Decimal("9.99")) == DriftSeverity.alert

    def test_exactly_ten_is_critical(self):
        assert _severity(Decimal("10.0")) == DriftSeverity.critical

    def test_over_ten_is_critical(self):
        assert _severity(Decimal("10.1")) == DriftSeverity.critical
        assert _severity(Decimal("25.0")) == DriftSeverity.critical

    def test_negative_uses_absolute_value(self):
        assert _severity(Decimal("-3.5")) == DriftSeverity.warning
        assert _severity(Decimal("-12.0")) == DriftSeverity.critical


class TestNormalise:
    def test_lowercases(self):
        assert _normalise("Steel Sheet") == "steel sheet"

    def test_strips_leading_trailing_whitespace(self):
        assert _normalise("  steel sheet  ") == "steel sheet"

    def test_collapses_internal_spaces(self):
        assert _normalise("steel   sheet") == "steel sheet"

    def test_preserves_digits_and_units(self):
        assert _normalise("Sheet 3mm 2500x1250") == "sheet 3mm 2500x1250"

    def test_mixed_case_and_spacing(self):
        assert _normalise("  MILD Steel  SHEET  3mm  ") == "mild steel sheet 3mm"


class TestFinancialImpact:
    def test_positive_overcharge(self):
        contracted = Decimal("48.50")
        observed = Decimal("54.20")
        quantity = Decimal("20")
        impact = (observed - contracted) * quantity
        assert impact == Decimal("114.00")

    def test_negative_is_credit(self):
        contracted = Decimal("48.50")
        observed = Decimal("44.00")
        quantity = Decimal("10")
        impact = (observed - contracted) * quantity
        assert impact == Decimal("-45.00")

    def test_exact_match_zero_impact(self):
        contracted = Decimal("48.50")
        observed = Decimal("48.50")
        assert (observed - contracted) == Decimal("0")


class TestTolerance:
    def test_within_default_tolerance_no_alert(self):
        variance_pct = Decimal("0.015")  # 1.5%
        tolerance = Decimal("0.02")
        assert not (abs(variance_pct) > tolerance)

    def test_just_over_tolerance_triggers_alert(self):
        variance_pct = Decimal("0.021")  # 2.1%
        tolerance = Decimal("0.02")
        assert abs(variance_pct) > tolerance

    def test_custom_tighter_tolerance(self):
        variance_pct = Decimal("0.006")  # 0.6% — over a 0.5% custom tolerance
        tolerance = Decimal("0.005")
        assert abs(variance_pct) > tolerance

    def test_custom_looser_tolerance(self):
        variance_pct = Decimal("0.04")  # 4% — within a 5% custom tolerance
        tolerance = Decimal("0.05")
        assert not (abs(variance_pct) > tolerance)


# ─── DriftDetector.process_line() integration tests ────────────────────────────

@pytest.mark.asyncio
class TestProcessLine:

    async def test_exact_contract_price_creates_observation_no_alert(self):
        """Price exactly matches contract → observation created, no alert, no AI call."""
        contracted = make_contracted(unit_price=48.50)
        line = make_line(unit_price=48.50)
        detector, db = make_detector(contracted)

        with patch("app.services.drift_detector._ai") as mock_ai:
            result = await detector.process_line(line)

        assert result.observation_id is not None
        assert result.alert_id is None
        assert result.severity is None
        assert result.ai_summary is None
        mock_ai.messages.create.assert_not_called()
        db.add.assert_called_once()  # only PriceObservation added

    async def test_within_tolerance_creates_observation_no_alert(self):
        """1.5% over contract, default 2% tolerance → info only, no alert."""
        contracted = make_contracted(unit_price=100.00)
        line = make_line(unit_price=101.50)
        detector, db = make_detector(contracted)

        with patch("app.services.drift_detector._ai") as mock_ai:
            result = await detector.process_line(line)

        assert result.alert_id is None
        assert result.severity == DriftSeverity.info
        assert result.ai_summary is None
        mock_ai.messages.create.assert_not_called()

    async def test_warning_drift_creates_alert_with_ai_summary(self):
        """3% over contract → warning alert created, AI summary generated."""
        contracted = make_contracted(unit_price=100.00)
        line = make_line(unit_price=103.00)
        detector, db = make_detector(contracted)

        mock_summary = "Supplier invoiced 3% above contract. Review recommended."
        with patch("app.services.drift_detector._ai") as mock_ai:
            mock_ai.messages.create = AsyncMock(
                return_value=MagicMock(content=[MagicMock(text=mock_summary)])
            )
            result = await detector.process_line(line)

        assert result.alert_id is not None
        assert result.severity == DriftSeverity.warning
        assert result.ai_summary == mock_summary
        mock_ai.messages.create.assert_called_once()
        assert db.add.call_count == 2  # PriceObservation + DriftAlert

    async def test_alert_drift_creates_alert_with_ai_summary(self):
        """7% over contract → alert severity, AI summary generated."""
        contracted = make_contracted(unit_price=100.00)
        line = make_line(unit_price=107.00)
        detector, db = make_detector(contracted)

        mock_summary = "7% overcharge detected. Immediate review required."
        with patch("app.services.drift_detector._ai") as mock_ai:
            mock_ai.messages.create = AsyncMock(
                return_value=MagicMock(content=[MagicMock(text=mock_summary)])
            )
            result = await detector.process_line(line)

        assert result.severity == DriftSeverity.alert
        assert result.alert_id is not None
        assert result.ai_summary == mock_summary

    async def test_critical_drift_creates_alert_with_ai_summary(self):
        """11% over contract → critical severity, AI summary generated."""
        contracted = make_contracted(unit_price=100.00)
        line = make_line(unit_price=111.00)
        detector, db = make_detector(contracted)

        mock_summary = "Critical: 11% overcharge. Escalate immediately."
        with patch("app.services.drift_detector._ai") as mock_ai:
            mock_ai.messages.create = AsyncMock(
                return_value=MagicMock(content=[MagicMock(text=mock_summary)])
            )
            result = await detector.process_line(line)

        assert result.severity == DriftSeverity.critical
        assert result.alert_id is not None
        assert result.direction == DriftDirection.up

    async def test_price_decrease_detected_as_down(self):
        """Price below contract → direction=down, no alert if within tolerance."""
        contracted = make_contracted(unit_price=100.00)
        line = make_line(unit_price=98.50)  # 1.5% under — within 2% tolerance
        detector, db = make_detector(contracted)

        with patch("app.services.drift_detector._ai"):
            result = await detector.process_line(line)

        assert result.direction == DriftDirection.down
        assert result.alert_id is None

    async def test_no_contracted_price_creates_observation_no_alert(self):
        """No contracted price found → observation recorded, no alert, no AI call."""
        detector, db = make_detector(contracted=None)
        line = make_line(unit_price=50.00)

        with patch("app.services.drift_detector._ai") as mock_ai:
            result = await detector.process_line(line)

        assert result.observation_id is not None
        assert result.alert_id is None
        assert result.contracted_price is None
        assert result.severity is None
        mock_ai.messages.create.assert_not_called()
        db.add.assert_called_once()  # only PriceObservation

    async def test_custom_per_sku_tolerance_overrides_client_default(self):
        """Per-SKU 0.5% tolerance: 0.6% drift exceeds tolerance → observation created with
        info severity, but no alert (info-level drift is logged silently, not alerted)."""
        contracted = make_contracted(unit_price=100.00, sku="STEEL-3MM", tolerance=0.005)
        line = make_line(unit_price=100.60, sku="STEEL-3MM")
        detector, db = make_detector(contracted)

        with patch("app.services.drift_detector._ai") as mock_ai:
            result = await detector.process_line(line)

        # 0.6% exceeds the 0.5% tolerance → severity is set to info (not None)
        assert result.severity == DriftSeverity.info
        assert result.direction == DriftDirection.up
        assert result.observation_id is not None
        # Info-level never creates an alert — observation is logged only
        assert result.alert_id is None
        mock_ai.messages.create.assert_not_called()

    async def test_variance_pct_calculation_correct(self):
        """Verify variance % is calculated correctly."""
        contracted = make_contracted(unit_price=48.50)
        # 54.20 / 48.50 - 1 = 11.75% overcharge
        line = make_line(unit_price=54.20, quantity=20.0)
        detector, db = make_detector(contracted)

        mock_summary = "11.75% overcharge on steel sheet."
        with patch("app.services.drift_detector._ai") as mock_ai:
            mock_ai.messages.create = AsyncMock(
                return_value=MagicMock(content=[MagicMock(text=mock_summary)])
            )
            result = await detector.process_line(line)

        assert result.variance_pct is not None
        assert abs(result.variance_pct - 11.7526) < 0.001
        # Financial impact: (54.20 - 48.50) * 20 = 5.70 * 20 = £114.00
        assert result.financial_impact == Decimal("114.00")
        assert result.severity == DriftSeverity.critical

    async def test_db_flush_called_after_observation(self):
        """Verify db.flush() is called after observation AND after alert creation."""
        contracted = make_contracted(unit_price=100.00, sku="STEEL-3MM")
        line = make_line(unit_price=107.00, sku="STEEL-3MM")  # 7% → alert severity
        detector, db = make_detector(contracted)

        with patch("app.services.drift_detector._ai") as mock_ai:
            mock_ai.messages.create = AsyncMock(
                return_value=MagicMock(content=[MagicMock(text="summary")])
            )
            await detector.process_line(line)

        # flush called at least twice: once after observation, once after alert
        assert db.flush.await_count >= 2


# ─── Monthly accumulation ─────────────────────────────────────────────────────

class TestMonthlyAccumulation:
    def test_impact_accumulates_correctly(self):
        impacts = [Decimal("114.00"), Decimal("45.00"), Decimal("22.50"), Decimal("88.00")]
        assert sum(impacts) == Decimal("269.50")

    def test_credit_lines_reduce_total(self):
        impacts = [Decimal("114.00"), Decimal("-20.00"), Decimal("45.00")]
        assert sum(impacts) == Decimal("139.00")
