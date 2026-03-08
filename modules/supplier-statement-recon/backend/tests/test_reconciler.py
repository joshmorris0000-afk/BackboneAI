"""
Tests for the Supplier Statement Reconciliation Engine.

Covers:
- Exact reference match (perfect reconciliation)
- Fuzzy reference match within tolerance
- Amount mismatch (same ref, different amount)
- Date mismatch (ref + amount match, dates differ beyond tolerance)
- Missing from ledger (statement line with no ledger counterpart)
- Missing from statement (ledger line with no statement counterpart)
- Unmatched ledger lines become on_ledger_only discrepancies
- Reference normalisation (_normalise_ref)
- Amount tolerance (_amounts_match)
- Date tolerance (_dates_within)
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.recon_data import (
    DiscrepancyType,
    LedgerLine,
    MatchStatus,
    ReconSession,
    StatementLine,
)
from app.services.reconciler import (
    ReconciliationEngine,
    MatchResult,
    _normalise_ref,
    _amounts_match,
    _dates_within,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _id() -> uuid.UUID:
    return uuid.uuid4()


CLIENT_ID = _id()
SUPPLIER_ID = _id()
SESSION_ID = _id()


def make_session(
    statement_total: float = 1000.00,
    statement_lines: list | None = None,
    ledger_lines: list | None = None,
) -> ReconSession:
    s = ReconSession()
    s.id = SESSION_ID
    s.client_id = CLIENT_ID
    s.supplier_id = SUPPLIER_ID
    s.statement_date = date(2026, 3, 1)
    s.period_from = date(2026, 2, 1)
    s.period_to = date(2026, 2, 28)
    s.statement_total = Decimal(str(statement_total))
    s.statement_currency = "GBP"
    s.status = "pending"
    s.matched_count = 0
    s.discrepancy_count = 0
    s.statement_lines = statement_lines or []
    s.ledger_lines = ledger_lines or []
    return s


def make_stmt(
    ref: str = "INV-001",
    our_ref: str | None = None,
    amount: float = 100.00,
    txn_date: date = date(2026, 2, 10),
    txn_type: str = "invoice",
) -> StatementLine:
    s = StatementLine()
    s.id = _id()
    s.session_id = SESSION_ID
    s.client_id = CLIENT_ID
    s.supplier_id = SUPPLIER_ID
    s.supplier_reference = ref
    s.our_reference = our_ref
    s.transaction_date = txn_date
    s.amount = Decimal(str(amount))
    s.transaction_type = txn_type
    s.match_status = MatchStatus.on_statement_only.value
    return s


def make_ledger(
    ref: str = "PO-001",
    supplier_ref: str | None = None,
    amount: float = 100.00,
    txn_date: date = date(2026, 2, 10),
    txn_type: str = "invoice",
) -> LedgerLine:
    l = LedgerLine()
    l.id = _id()
    l.session_id = SESSION_ID
    l.client_id = CLIENT_ID
    l.supplier_id = SUPPLIER_ID
    l.our_reference = ref
    l.supplier_reference = supplier_ref
    l.transaction_date = txn_date
    l.amount = Decimal(str(amount))
    l.transaction_type = txn_type
    l.match_status = MatchStatus.on_ledger_only.value
    return l


def make_engine(db: AsyncMock | None = None) -> ReconciliationEngine:
    if db is None:
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
    return ReconciliationEngine(
        db=db,
        amount_tolerance=Decimal("0.01"),
        date_tolerance_days=7,
        reference_fuzzy_threshold=85,
    )


# ─── Pure function tests ───────────────────────────────────────────────────────

class TestNormaliseRef:
    def test_lowercases(self):
        assert _normalise_ref("INV-001") == "inv 001"

    def test_replaces_dashes_with_space(self):
        assert _normalise_ref("INV-2026-001") == "inv 2026 001"

    def test_replaces_slashes_with_space(self):
        assert _normalise_ref("PO/2026/001") == "po 2026 001"

    def test_strips_leading_trailing_whitespace(self):
        assert _normalise_ref("  INV 001  ") == "inv 001"

    def test_same_ref_different_separators_match(self):
        assert _normalise_ref("INV-001") == _normalise_ref("INV/001")
        assert _normalise_ref("PO-2026-001") == _normalise_ref("PO 2026 001")


class TestAmountsMatch:
    def test_exact_match(self):
        assert _amounts_match(Decimal("100.00"), Decimal("100.00"), Decimal("0.01"))

    def test_within_tolerance(self):
        assert _amounts_match(Decimal("100.00"), Decimal("100.01"), Decimal("0.01"))

    def test_just_over_tolerance(self):
        assert not _amounts_match(Decimal("100.00"), Decimal("100.02"), Decimal("0.01"))

    def test_negative_amounts(self):
        assert _amounts_match(Decimal("-50.00"), Decimal("-50.00"), Decimal("0.01"))

    def test_large_difference(self):
        assert not _amounts_match(Decimal("1000.00"), Decimal("1100.00"), Decimal("0.01"))


class TestDatesWithin:
    def test_same_date(self):
        assert _dates_within(date(2026, 2, 10), date(2026, 2, 10), 7)

    def test_within_tolerance(self):
        assert _dates_within(date(2026, 2, 10), date(2026, 2, 15), 7)

    def test_exactly_at_tolerance(self):
        assert _dates_within(date(2026, 2, 10), date(2026, 2, 17), 7)

    def test_just_over_tolerance(self):
        assert not _dates_within(date(2026, 2, 10), date(2026, 2, 18), 7)

    def test_direction_independent(self):
        assert _dates_within(date(2026, 2, 17), date(2026, 2, 10), 7)


# ─── Engine matching tests ─────────────────────────────────────────────────────

class TestEngineMatching:

    def test_exact_supplier_ref_match(self):
        """Ledger has supplier_reference matching statement supplier_reference."""
        stmt = make_stmt(ref="INV-001", amount=100.00)
        ledger = make_ledger(ref="PO-001", supplier_ref="INV-001", amount=100.00)
        engine = make_engine()

        result = engine._match_statement_line(stmt, [ledger], set())

        assert result.status == MatchStatus.matched
        assert result.ledger_line is ledger
        assert result.discrepancy_type is None

    def test_our_reference_match(self):
        """Statement includes our_reference matching ledger our_reference."""
        stmt = make_stmt(ref="INV-001", our_ref="PO-001", amount=250.00)
        ledger = make_ledger(ref="PO-001", amount=250.00)
        engine = make_engine()

        result = engine._match_statement_line(stmt, [ledger], set())

        assert result.status == MatchStatus.matched
        assert result.ledger_line is ledger

    def test_fuzzy_reference_match(self):
        """Slightly different reference formats still match via fuzzy matching."""
        stmt = make_stmt(ref="INV-2026-001", amount=500.00)
        ledger = make_ledger(ref="PO-100", supplier_ref="INV2026001", amount=500.00)
        engine = make_engine()

        result = engine._match_statement_line(stmt, [ledger], set())

        assert result.status == MatchStatus.matched

    def test_amount_mismatch(self):
        """Same reference but amounts differ → amount_mismatch discrepancy."""
        stmt = make_stmt(ref="INV-001", amount=100.00)
        ledger = make_ledger(ref="PO-001", supplier_ref="INV-001", amount=95.00)
        engine = make_engine()

        result = engine._match_statement_line(stmt, [ledger], set())

        assert result.status == MatchStatus.amount_mismatch
        assert result.discrepancy_type == DiscrepancyType.amount_difference
        assert result.financial_impact == Decimal("5.00")

    def test_date_mismatch(self):
        """Fuzzy ref match (same ref, one has year prefix), amounts match, but dates
        19 days apart (> 7 day tolerance) → date_mismatch.

        Uses 'INV-2026-001' vs 'INV-001': after normalisation these become
        'inv 2026 001' vs 'inv 001'. They are NOT exact matches, but token_set_ratio
        scores 100% because 'inv 001' is a token-subset of 'inv 2026 001'. This
        forces the fuzzy path which enforces the date tolerance check.
        """
        stmt = make_stmt(ref="INV-2026-001", amount=100.00, txn_date=date(2026, 2, 1))
        ledger = make_ledger(ref="PO-001", supplier_ref="INV-001", amount=100.00, txn_date=date(2026, 2, 20))
        engine = make_engine()

        result = engine._match_statement_line(stmt, [ledger], set())

        assert result.status == MatchStatus.date_mismatch
        assert result.discrepancy_type == DiscrepancyType.date_difference

    def test_no_match_missing_from_ledger(self):
        """Statement line with no ledger counterpart → on_statement_only."""
        stmt = make_stmt(ref="INV-999", amount=300.00)
        engine = make_engine()

        result = engine._match_statement_line(stmt, [], set())

        assert result.status == MatchStatus.on_statement_only
        assert result.discrepancy_type == DiscrepancyType.missing_from_ledger
        assert result.financial_impact == Decimal("300.00")

    def test_already_matched_ledger_skipped(self):
        """A ledger line already matched cannot be matched again."""
        stmt1 = make_stmt(ref="INV-001", amount=100.00)
        stmt2 = make_stmt(ref="INV-001", amount=100.00)  # duplicate on statement
        ledger = make_ledger(ref="PO-001", supplier_ref="INV-001", amount=100.00)
        engine = make_engine()

        # Match stmt1 first
        r1 = engine._match_statement_line(stmt1, [ledger], set())
        already_matched = {str(ledger.id)}

        # stmt2 should not get the same ledger
        r2 = engine._match_statement_line(stmt2, [ledger], already_matched)

        assert r1.status == MatchStatus.matched
        assert r2.status == MatchStatus.on_statement_only

    def test_amount_only_fallback_match(self):
        """When reference doesn't match, amount + date + type is a fallback."""
        stmt = make_stmt(ref="COMPLETELY-DIFFERENT-REF", amount=750.00, txn_date=date(2026, 2, 10))
        ledger = make_ledger(ref="PO-555", amount=750.00, txn_date=date(2026, 2, 12))
        engine = make_engine()

        result = engine._match_statement_line(stmt, [ledger], set())

        assert result.status == MatchStatus.matched


# ─── Full reconciliation run tests ────────────────────────────────────────────

@pytest.mark.asyncio
class TestFullRun:

    async def test_clean_reconciliation_no_discrepancies(self):
        """All statement lines match ledger lines exactly — no discrepancies."""
        stmt = make_stmt(ref="INV-001", our_ref="PO-001", amount=500.00)
        ledger = make_ledger(ref="PO-001", supplier_ref="INV-001", amount=500.00)
        session = make_session(statement_total=500.00, statement_lines=[stmt], ledger_lines=[ledger])

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        engine = ReconciliationEngine(db=db, amount_tolerance=Decimal("0.01"), date_tolerance_days=7)

        with patch("app.services.reconciler._ai") as mock_ai:
            results = await engine.run(session)

        assert session.matched_count == 1
        assert session.discrepancy_count == 0
        assert session.status == "completed"
        db.add.assert_not_called()  # no discrepancies to add

    async def test_unmatched_ledger_line_becomes_discrepancy(self):
        """Ledger line with no statement counterpart → on_ledger_only discrepancy."""
        ledger = make_ledger(ref="PO-999", amount=200.00)
        session = make_session(statement_total=0.00, statement_lines=[], ledger_lines=[ledger])

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        engine = ReconciliationEngine(db=db, amount_tolerance=Decimal("0.01"), date_tolerance_days=7)

        with patch("app.services.reconciler._ai") as mock_ai:
            mock_ai.messages.create = AsyncMock(
                return_value=MagicMock(content=[MagicMock(text="Ledger line has no counterpart on statement.")])
            )
            results = await engine.run(session)

        assert session.discrepancy_count == 1
        assert ledger.match_status == MatchStatus.on_ledger_only.value

    async def test_mixed_session_counts_correctly(self):
        """2 matches, 1 missing-from-ledger, 1 missing-from-statement."""
        stmt_matched = make_stmt(ref="INV-001", our_ref="PO-001", amount=100.00)
        stmt_matched2 = make_stmt(ref="INV-002", our_ref="PO-002", amount=200.00)
        stmt_missing = make_stmt(ref="INV-GHOST", amount=50.00)  # not in ledger

        ledger_matched = make_ledger(ref="PO-001", supplier_ref="INV-001", amount=100.00)
        ledger_matched2 = make_ledger(ref="PO-002", supplier_ref="INV-002", amount=200.00)
        ledger_extra = make_ledger(ref="PO-EXTRA", amount=75.00)  # not on statement

        session = make_session(
            statement_total=350.00,
            statement_lines=[stmt_matched, stmt_matched2, stmt_missing],
            ledger_lines=[ledger_matched, ledger_matched2, ledger_extra],
        )

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        engine = ReconciliationEngine(db=db, amount_tolerance=Decimal("0.01"), date_tolerance_days=7)

        with patch("app.services.reconciler._ai") as mock_ai:
            mock_ai.messages.create = AsyncMock(
                return_value=MagicMock(content=[MagicMock(text="Discrepancy explanation.")])
            )
            results = await engine.run(session)

        assert session.matched_count == 2
        assert session.discrepancy_count == 2  # INV-GHOST + PO-EXTRA
        assert session.status == "completed"
