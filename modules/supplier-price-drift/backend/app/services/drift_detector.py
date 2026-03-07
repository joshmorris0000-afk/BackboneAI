"""
Supplier Price Drift Detector — core engine.

Processes every invoice line item against contracted prices to detect:
- Gradual price creep above contracted rates (most common)
- Sudden price spikes on specific SKUs
- Consistent overcharging patterns across multiple invoices
- Supplier-wide inflation trends

The engine is called:
1. Automatically when a new invoice is ingested (real-time detection)
2. On a nightly batch job that re-evaluates the last 90 days

Severity thresholds are configurable per client and per contracted price.
AI (Claude) generates a plain-English summary for each alert so AP teams
understand exactly what they're looking at without needing to interpret numbers.
"""
import re
from dataclasses import dataclass
from datetime import UTC, datetime, date
from decimal import Decimal

import anthropic
from rapidfuzz import fuzz
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.price_data import (
    AlertStatus,
    ContractedPrice,
    DriftAlert,
    DriftDirection,
    DriftSeverity,
    PriceObservation,
)

settings = get_settings()
_ai = anthropic.Anthropic(api_key=settings.anthropic_api_key)


@dataclass
class InvoiceLine:
    """Minimal invoice line passed in from the calling system."""
    invoice_id: str
    invoice_number: str
    invoice_date: date
    supplier_id: str
    client_id: str
    description: str
    sku: str | None
    unit_price: Decimal
    quantity: Decimal
    currency: str = "GBP"


@dataclass
class DriftResult:
    observation_id: str
    alert_id: str | None
    severity: DriftSeverity | None
    direction: DriftDirection | None
    contracted_price: Decimal | None
    observed_price: Decimal
    variance_pct: float | None
    financial_impact: Decimal | None
    ai_summary: str | None


def _normalise(text: str) -> str:
    """Normalise product description for fuzzy matching."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _severity(variance_pct: Decimal) -> DriftSeverity:
    pct = abs(float(variance_pct))
    if pct < 2:
        return DriftSeverity.info
    elif pct < 5:
        return DriftSeverity.warning
    elif pct < 10:
        return DriftSeverity.alert
    return DriftSeverity.critical


class DriftDetector:

    def __init__(self, db: AsyncSession, client_default_tolerance: Decimal = Decimal("0.02")):
        self.db = db
        self.client_default_tolerance = client_default_tolerance

    async def process_line(self, line: InvoiceLine) -> DriftResult:
        """
        Process a single invoice line:
        1. Find matching contracted price
        2. Calculate drift
        3. Create observation record
        4. Create alert if threshold exceeded
        5. Generate AI summary for alerts
        """
        contracted = await self._find_contracted_price(line)

        variance = None
        variance_pct = None
        financial_impact = None
        severity = None
        direction = None

        if contracted:
            variance = line.unit_price - contracted.unit_price
            variance_pct = (variance / contracted.unit_price * 100).quantize(Decimal("0.0001"))
            financial_impact = (variance * line.quantity).quantize(Decimal("0.01"))
            direction = DriftDirection.up if variance > 0 else DriftDirection.down

            tolerance = contracted.tolerance_pct or self.client_default_tolerance
            if abs(variance / contracted.unit_price) > tolerance:
                severity = _severity(variance_pct)
            else:
                severity = DriftSeverity.info if variance != 0 else None

        # Write observation
        obs = PriceObservation(
            client_id=line.client_id,
            supplier_id=line.supplier_id,
            contracted_price_id=contracted.id if contracted else None,
            invoice_id=line.invoice_id,
            invoice_number=line.invoice_number,
            invoice_date=line.invoice_date,
            sku=line.sku,
            description_raw=line.description,
            observed_unit_price=line.unit_price,
            quantity=line.quantity,
            currency=line.currency,
            contracted_unit_price=contracted.unit_price if contracted else None,
            price_variance=variance,
            price_variance_pct=variance_pct,
            financial_impact=financial_impact,
            drift_severity=severity.value if severity else None,
            drift_direction=direction.value if direction else None,
        )
        self.db.add(obs)
        await self.db.flush()

        alert_id = None
        ai_summary = None

        # Raise alert if severity warrants it
        if severity and severity != DriftSeverity.info:
            monthly_totals = await self._monthly_context(line)
            ai_summary = await self._generate_ai_summary(line, contracted, variance_pct, financial_impact, monthly_totals, severity)

            alert = DriftAlert(
                client_id=line.client_id,
                supplier_id=line.supplier_id,
                observation_id=obs.id,
                severity=severity.value,
                direction=direction.value,
                status=AlertStatus.open,
                total_drift_this_month=monthly_totals["total_drift"],
                occurrences_this_month=monthly_totals["occurrences"],
                ai_summary=ai_summary,
            )
            self.db.add(alert)
            await self.db.flush()
            alert_id = str(alert.id)

        return DriftResult(
            observation_id=str(obs.id),
            alert_id=alert_id,
            severity=severity,
            direction=direction,
            contracted_price=contracted.unit_price if contracted else None,
            observed_price=line.unit_price,
            variance_pct=float(variance_pct) if variance_pct is not None else None,
            financial_impact=financial_impact,
            ai_summary=ai_summary,
        )

    async def _find_contracted_price(self, line: InvoiceLine) -> ContractedPrice | None:
        """
        Find the best matching contracted price for this line item.
        Priority: SKU exact → description fuzzy match → part number.
        """
        today = date.today()

        # Strategy 1: SKU exact match
        if line.sku:
            result = await self.db.execute(
                select(ContractedPrice).where(
                    and_(
                        ContractedPrice.client_id == line.client_id,
                        ContractedPrice.supplier_id == line.supplier_id,
                        ContractedPrice.sku == line.sku,
                        ContractedPrice.valid_from <= today,
                        (ContractedPrice.valid_to >= today) | (ContractedPrice.valid_to.is_(None)),
                    )
                )
            )
            cp = result.scalar_one_or_none()
            if cp:
                return cp

        # Strategy 2: Description fuzzy match against all contracted prices for this supplier
        result = await self.db.execute(
            select(ContractedPrice).where(
                and_(
                    ContractedPrice.client_id == line.client_id,
                    ContractedPrice.supplier_id == line.supplier_id,
                    ContractedPrice.valid_from <= today,
                    (ContractedPrice.valid_to >= today) | (ContractedPrice.valid_to.is_(None)),
                )
            )
        )
        candidates = result.scalars().all()

        norm_desc = _normalise(line.description)
        best_score = 0
        best_cp = None

        for cp in candidates:
            score = fuzz.token_set_ratio(norm_desc, cp.description_normalised)
            if score > best_score:
                best_score = score
                best_cp = cp

        # Require ≥ 80% similarity to treat as a match
        return best_cp if best_score >= 80 else None

    async def _monthly_context(self, line: InvoiceLine) -> dict:
        """Get this month's running drift totals for this supplier, for alert context."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(
                func.sum(PriceObservation.financial_impact),
                func.count(PriceObservation.id),
            ).where(
                and_(
                    PriceObservation.client_id == line.client_id,
                    PriceObservation.supplier_id == line.supplier_id,
                    func.extract("year", PriceObservation.invoice_date) == now.year,
                    func.extract("month", PriceObservation.invoice_date) == now.month,
                    PriceObservation.financial_impact > 0,
                )
            )
        )
        row = result.one()
        return {
            "total_drift": row[0] or Decimal("0"),
            "occurrences": row[1] or 0,
        }

    async def _generate_ai_summary(
        self,
        line: InvoiceLine,
        contracted: ContractedPrice,
        variance_pct: Decimal,
        financial_impact: Decimal,
        monthly_context: dict,
        severity: DriftSeverity,
    ) -> str:
        """
        Use Claude to generate a plain-English summary of the drift alert.
        Written for an AP manager who needs to understand the issue quickly
        and decide whether to raise a dispute with the supplier.
        """
        prompt = f"""You are writing a concise alert summary for an Accounts Payable manager at a UK manufacturing business.

A supplier has invoiced at a price above their contracted rate. Write a 2–3 sentence plain English summary that:
1. States clearly what happened (product, supplier, % overcharge)
2. Quantifies the financial impact on this invoice
3. Notes the month-to-date total if relevant
4. Recommends a specific action

Keep it factual and professional. No waffle. Maximum 60 words.

ALERT DATA:
- Supplier: {line.supplier_id}
- Product: {line.description}
- SKU: {line.sku or 'not specified'}
- Contracted unit price: £{contracted.unit_price:.4f}
- Invoiced unit price: £{line.unit_price:.4f}
- Variance: {float(variance_pct):+.2f}%
- Quantity invoiced: {line.quantity}
- Financial impact this line: £{financial_impact:.2f}
- Month-to-date drift from this supplier: £{monthly_context['total_drift']:.2f} across {monthly_context['occurrences']} lines
- Severity: {severity.value}

Write the summary only — no labels, no JSON."""

        message = _ai.messages.create(
            model=settings.ai_model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()


async def process_invoice_lines(
    db: AsyncSession,
    lines: list[InvoiceLine],
    client_tolerance: Decimal = Decimal("0.02"),
) -> list[DriftResult]:
    """Entry point: process all lines from a single invoice."""
    detector = DriftDetector(db, client_tolerance)
    results = []
    for line in lines:
        result = await detector.process_line(line)
        results.append(result)
    return results
