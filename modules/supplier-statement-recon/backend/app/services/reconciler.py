"""
Supplier Statement Reconciliation Engine.

Matches statement lines (what the supplier says you owe) against ledger lines
(what your ERP has recorded) using a priority-ordered matching strategy:

1. Exact reference match (supplier ref = our ref, or vice versa)
2. Fuzzy reference match (≥85% similarity) + amount within tolerance
3. Amount-only match (same amount ± 1p, within date tolerance)
4. Anything unmatched → discrepancy

For each discrepancy, Claude writes a plain-English explanation so AP staff
know immediately what to investigate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Optional

import anthropic
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.recon_data import (
    DiscrepancyType,
    LedgerLine,
    MatchStatus,
    ReconDiscrepancy,
    ReconSession,
    StatementLine,
)

settings = get_settings()
_ai = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def _normalise_ref(ref: str) -> str:
    """Normalise a reference number for matching.

    Replaces separators (dashes, slashes, whitespace) with single spaces and
    lowercases. Keeping spaces as token boundaries lets rapidfuzz token_set_ratio
    correctly identify subset matches — e.g. 'INV 001' is a token-subset of
    'INV 2026 001', scoring 100% even though the strings differ.
    """
    return re.sub(r"[\s\-/]+", " ", ref.lower().strip())


def _amounts_match(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    return abs(a - b) <= tolerance


def _dates_within(d1: date, d2: date, tolerance_days: int) -> bool:
    return abs((d1 - d2).days) <= tolerance_days


@dataclass
class MatchResult:
    statement_line: StatementLine
    ledger_line: Optional[LedgerLine]
    status: MatchStatus
    discrepancy_type: Optional[DiscrepancyType]
    financial_impact: Decimal


class ReconciliationEngine:

    def __init__(
        self,
        db: AsyncSession,
        amount_tolerance: Decimal = Decimal("0.01"),
        date_tolerance_days: int = 7,
        reference_fuzzy_threshold: int = 85,
    ):
        self.db = db
        self.amount_tolerance = amount_tolerance
        self.date_tolerance_days = date_tolerance_days
        self.reference_fuzzy_threshold = reference_fuzzy_threshold

    async def run(self, session: ReconSession) -> list[MatchResult]:
        """
        Match all statement lines against ledger lines for a reconciliation session.
        Returns the full list of match results; writes discrepancy records to DB.
        """
        statement_lines: list[StatementLine] = list(session.statement_lines)
        ledger_lines: list[LedgerLine] = list(session.ledger_lines)

        results: list[MatchResult] = []
        matched_ledger_ids: set[str] = set()

        # ── Pass 1: match each statement line ──────────────────────────────────
        for stmt in statement_lines:
            result = self._match_statement_line(stmt, ledger_lines, matched_ledger_ids)
            if result.ledger_line:
                matched_ledger_ids.add(str(result.ledger_line.id))
                # Update match status on both lines
                stmt.match_status = result.status.value
                result.ledger_line.match_status = result.status.value
                stmt.matched_ledger_line_id = result.ledger_line.id
                result.ledger_line.matched_statement_line_id = stmt.id

            results.append(result)

        # ── Pass 2: unmatched ledger lines → on_ledger_only ───────────────────
        for ledger in ledger_lines:
            if str(ledger.id) not in matched_ledger_ids:
                result = MatchResult(
                    statement_line=None,
                    ledger_line=ledger,
                    status=MatchStatus.on_ledger_only,
                    discrepancy_type=DiscrepancyType.missing_from_statement,
                    financial_impact=ledger.amount,
                )
                ledger.match_status = MatchStatus.on_ledger_only.value
                results.append(result)

        # ── Pass 3: write discrepancy records for non-matched items ────────────
        discrepancies: list[ReconDiscrepancy] = []
        for r in results:
            if r.status not in (MatchStatus.matched,):
                disc = await self._create_discrepancy(session, r)
                if disc:
                    discrepancies.append(disc)
                    self.db.add(disc)

        await self.db.flush()

        # ── Pass 4: generate AI summary for the session ───────────────────────
        matched_count = sum(1 for r in results if r.status == MatchStatus.matched)
        session.matched_count = matched_count
        session.discrepancy_count = len(discrepancies)
        session.total_discrepancy_value = sum(abs(d.financial_impact) for d in discrepancies)

        ledger_total = sum(l.amount for l in ledger_lines)
        session.ledger_total = ledger_total
        session.variance = session.statement_total - ledger_total

        if discrepancies:
            session.ai_summary = await self._generate_session_summary(session, discrepancies)

        from app.models.recon_data import ReconciliationStatus
        session.status = ReconciliationStatus.completed.value

        await self.db.flush()
        return results

    def _match_statement_line(
        self,
        stmt: StatementLine,
        ledger_lines: list[LedgerLine],
        already_matched: set[str],
    ) -> MatchResult:
        """Try each matching strategy in priority order."""
        available = [l for l in ledger_lines if str(l.id) not in already_matched]

        # Strategy 1: Exact reference match (our ref on statement = our ref in ledger)
        for ledger in available:
            if self._exact_ref_match(stmt, ledger):
                if _amounts_match(stmt.amount, ledger.amount, self.amount_tolerance):
                    return MatchResult(stmt, ledger, MatchStatus.matched, None, Decimal("0"))
                else:
                    return MatchResult(
                        stmt, ledger, MatchStatus.amount_mismatch,
                        DiscrepancyType.amount_difference,
                        stmt.amount - ledger.amount,
                    )

        # Strategy 2: Fuzzy reference match + amount tolerance
        best_score = 0
        best_candidate = None
        norm_stmt = _normalise_ref(stmt.supplier_reference)

        for ledger in available:
            # Check both reference fields
            refs_to_check = [ledger.our_reference]
            if ledger.supplier_reference:
                refs_to_check.append(ledger.supplier_reference)

            for ref in refs_to_check:
                score = fuzz.token_set_ratio(norm_stmt, _normalise_ref(ref))
                if score > best_score:
                    best_score = score
                    best_candidate = ledger

        if best_score >= self.reference_fuzzy_threshold and best_candidate:
            if _amounts_match(stmt.amount, best_candidate.amount, self.amount_tolerance):
                if _dates_within(stmt.transaction_date, best_candidate.transaction_date, self.date_tolerance_days):
                    return MatchResult(stmt, best_candidate, MatchStatus.matched, None, Decimal("0"))
                else:
                    return MatchResult(
                        stmt, best_candidate, MatchStatus.date_mismatch,
                        DiscrepancyType.date_difference,
                        Decimal("0"),
                    )
            else:
                return MatchResult(
                    stmt, best_candidate, MatchStatus.amount_mismatch,
                    DiscrepancyType.amount_difference,
                    stmt.amount - best_candidate.amount,
                )

        # Strategy 3: Amount-only match within date tolerance (last resort)
        for ledger in available:
            if (
                _amounts_match(stmt.amount, ledger.amount, self.amount_tolerance)
                and _dates_within(stmt.transaction_date, ledger.transaction_date, self.date_tolerance_days)
                and stmt.transaction_type == ledger.transaction_type
            ):
                return MatchResult(stmt, ledger, MatchStatus.matched, None, Decimal("0"))

        # No match found
        return MatchResult(
            stmt, None, MatchStatus.on_statement_only,
            DiscrepancyType.missing_from_ledger,
            stmt.amount,
        )

    def _exact_ref_match(self, stmt: StatementLine, ledger: LedgerLine) -> bool:
        """True if any reference pair is an exact normalised match."""
        stmt_refs = {_normalise_ref(stmt.supplier_reference)}
        if stmt.our_reference:
            stmt_refs.add(_normalise_ref(stmt.our_reference))

        ledger_refs = {_normalise_ref(ledger.our_reference)}
        if ledger.supplier_reference:
            ledger_refs.add(_normalise_ref(ledger.supplier_reference))

        return bool(stmt_refs & ledger_refs)

    async def _create_discrepancy(
        self,
        session: ReconSession,
        result: MatchResult,
    ) -> Optional[ReconDiscrepancy]:
        if result.discrepancy_type is None:
            return None

        explanation = await self._generate_discrepancy_explanation(result)

        return ReconDiscrepancy(
            session_id=session.id,
            client_id=session.client_id,
            supplier_id=session.supplier_id,
            discrepancy_type=result.discrepancy_type.value,
            status=MatchStatus.on_statement_only.value,
            statement_line_id=result.statement_line.id if result.statement_line else None,
            ledger_line_id=result.ledger_line.id if result.ledger_line else None,
            financial_impact=abs(result.financial_impact),
            ai_explanation=explanation,
        )

    async def _generate_discrepancy_explanation(self, result: MatchResult) -> str:
        """Generate a concise plain-English explanation of this specific discrepancy."""
        stmt = result.statement_line
        ledger = result.ledger_line

        context_parts = []
        if stmt:
            context_parts.append(
                f"Statement line: ref={stmt.supplier_reference}, date={stmt.transaction_date}, "
                f"amount=£{stmt.amount:.2f}, type={stmt.transaction_type}"
            )
        if ledger:
            context_parts.append(
                f"Ledger line: ref={ledger.our_reference}, date={ledger.transaction_date}, "
                f"amount=£{ledger.amount:.2f}, type={ledger.transaction_type}"
            )

        prompt = f"""You are writing a concise discrepancy note for an Accounts Payable manager reconciling a supplier statement.

Discrepancy type: {result.discrepancy_type.value if result.discrepancy_type else 'unknown'}
Financial impact: £{abs(result.financial_impact):.2f}

{chr(10).join(context_parts)}

Write 1–2 sentences explaining what the discrepancy is and what the AP manager should do.
Maximum 40 words. No labels. Plain English."""

        try:
            message = await _ai.messages.create(
                model=settings.ai_model,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception:
            return f"Discrepancy: {result.discrepancy_type.value if result.discrepancy_type else 'unknown'} — financial impact £{abs(result.financial_impact):.2f}."

    async def _generate_session_summary(
        self,
        session: ReconSession,
        discrepancies: list[ReconDiscrepancy],
    ) -> str:
        """Generate an executive summary of the full reconciliation result."""
        type_counts: dict[str, int] = {}
        for d in discrepancies:
            type_counts[d.discrepancy_type] = type_counts.get(d.discrepancy_type, 0) + 1

        prompt = f"""You are writing a reconciliation summary for an Accounts Payable manager.

Supplier statement reconciliation complete:
- Statement total: £{session.statement_total:.2f}
- Ledger total: £{session.ledger_total:.2f}
- Variance: £{session.variance:.2f} (positive = supplier overstates balance)
- Lines matched cleanly: {session.matched_count}
- Discrepancies requiring action: {session.discrepancy_count}
- Total discrepancy value: £{float(session.total_discrepancy_value or 0):.2f}
- Discrepancy breakdown: {type_counts}

Write a 3–4 sentence plain English summary:
1. Overall result (reconciled or discrepancies found)
2. Most significant issue(s) to address
3. Recommended next action

Maximum 80 words. No labels. Written for an AP manager."""

        try:
            message = await _ai.messages.create(
                model=settings.ai_model,
                max_tokens=settings.ai_max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception:
            return (
                f"Reconciliation complete. {session.matched_count} lines matched, "
                f"{session.discrepancy_count} discrepancies found totalling "
                f"£{float(session.total_discrepancy_value or 0):.2f}. "
                f"Statement variance: £{float(session.variance or 0):.2f}."
            )
