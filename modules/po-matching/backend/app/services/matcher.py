"""
3-Way Purchase Order Matching Engine.

Orchestrates:
1. Supplier resolution (extracted name → known supplier record)
2. PO lookup (by PO reference, supplier, date window)
3. GRN lookup (linked to matched PO)
4. Line-level matching (price + quantity variance calculation)
5. Overall status determination
6. Auto-approval evaluation
7. Fraud flag escalation

All matching decisions are recorded with the reasoning so they can be
audited and explained to a human reviewer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import ClientConfig
from app.models.documents import GoodsReceiptLine, GoodsReceiptNote, Invoice, InvoiceLine, PurchaseOrder, PurchaseOrderLine
from app.models.match import LineMatchStatus, MatchedBy, MatchLineResult, MatchResult, MatchStatus
from app.models.supplier import Supplier, SupplierAlias
from app.services.ai_extractor import InvoiceExtraction


@dataclass
class LineMatchDecision:
    invoice_line: InvoiceLine
    po_line: PurchaseOrderLine | None
    grn_line: GoodsReceiptLine | None
    status: LineMatchStatus
    price_variance: Decimal
    price_variance_pct: Decimal
    qty_variance: Decimal
    financial_exposure: Decimal
    reason: str


@dataclass
class MatchDecision:
    status: MatchStatus
    score: Decimal
    po: PurchaseOrder | None
    grn: GoodsReceiptNote | None
    line_decisions: list[LineMatchDecision]
    discrepancy_total: Decimal
    can_auto_approve: bool
    auto_approve_block_reasons: list[str]


class MatchingEngine:
    def __init__(self, db: AsyncSession, config: ClientConfig):
        self.db = db
        self.config = config

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────────

    async def match(self, invoice: Invoice) -> MatchDecision:
        """Run the full 3-way match for an invoice. Returns a MatchDecision."""

        # 1. Resolve supplier
        supplier = await self._resolve_supplier(invoice)

        # 2. Find best-matching PO
        po = await self._find_po(invoice, supplier)
        if po is None:
            return MatchDecision(
                status=MatchStatus.no_po_found,
                score=Decimal("0"),
                po=None,
                grn=None,
                line_decisions=[],
                discrepancy_total=invoice.grand_total,
                can_auto_approve=False,
                auto_approve_block_reasons=["No matching purchase order found"],
            )

        # 3. Supplier mismatch check (PO supplier vs invoice supplier)
        if not await self._suppliers_match(invoice, po):
            return MatchDecision(
                status=MatchStatus.supplier_mismatch,
                score=Decimal("0.2"),
                po=po,
                grn=None,
                line_decisions=[],
                discrepancy_total=invoice.grand_total,
                can_auto_approve=False,
                auto_approve_block_reasons=["Supplier on invoice does not match supplier on PO"],
            )

        # 4. Find GRN
        grn = await self._find_grn(po, invoice.invoice_date)

        # 5. Line-level matching
        line_decisions = await self._match_lines(invoice, po, grn)

        # 6. Overall status
        status = self._determine_status(line_decisions, grn)

        # 7. Discrepancy total
        discrepancy_total = sum(ld.financial_exposure for ld in line_decisions)

        # 8. Match score
        score = self._calculate_score(line_decisions, status)

        # 9. Auto-approval eligibility
        can_auto, block_reasons = self._evaluate_auto_approval(
            invoice, status, line_decisions, discrepancy_total
        )

        return MatchDecision(
            status=status,
            score=score,
            po=po,
            grn=grn,
            line_decisions=line_decisions,
            discrepancy_total=discrepancy_total,
            can_auto_approve=can_auto,
            auto_approve_block_reasons=block_reasons,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step 1 — Supplier resolution
    # ──────────────────────────────────────────────────────────────────────────

    async def _resolve_supplier(self, invoice: Invoice) -> Supplier | None:
        client_id = invoice.client_id
        name = invoice.supplier_name_raw

        # Priority 1: VAT number exact match
        if invoice.supplier_vat_number:
            result = await self.db.execute(
                select(Supplier).where(
                    and_(Supplier.client_id == client_id, Supplier.vat_number == invoice.supplier_vat_number)
                )
            )
            supplier = result.scalar_one_or_none()
            if supplier:
                return supplier

        # Priority 2: Canonical name exact (case-insensitive)
        result = await self.db.execute(
            select(Supplier).where(
                and_(Supplier.client_id == client_id, Supplier.canonical_name.ilike(name))
            )
        )
        supplier = result.scalar_one_or_none()
        if supplier:
            return supplier

        # Priority 3: Alias table
        result = await self.db.execute(
            select(SupplierAlias).where(SupplierAlias.alias.ilike(name))
        )
        alias = result.scalar_one_or_none()
        if alias:
            return await self.db.get(Supplier, alias.supplier_id)

        # Priority 4: Fuzzy match over all client suppliers
        all_suppliers = (
            await self.db.execute(select(Supplier).where(Supplier.client_id == client_id))
        ).scalars().all()

        best_score = 0
        best_supplier = None
        for s in all_suppliers:
            score = fuzz.token_set_ratio(name.lower(), s.canonical_name.lower())
            if score > best_score:
                best_score = score
                best_supplier = s

        if best_score >= 85:
            return best_supplier

        return None  # unresolved — will cause supplier_mismatch if PO also unresolved

    # ──────────────────────────────────────────────────────────────────────────
    # Step 2 — PO lookup
    # ──────────────────────────────────────────────────────────────────────────

    async def _find_po(self, invoice: Invoice, supplier: Supplier | None) -> PurchaseOrder | None:
        client_id = invoice.client_id

        # Strategy 1: Direct PO reference match
        if invoice.po_reference_raw:
            po_ref = invoice.po_reference_raw.strip()
            result = await self.db.execute(
                select(PurchaseOrder).where(
                    and_(
                        PurchaseOrder.client_id == client_id,
                        PurchaseOrder.po_number.ilike(f"%{po_ref}%"),
                    )
                )
            )
            po = result.scalar_one_or_none()
            if po:
                return po

        # Strategy 2: Supplier + date window + approximate total
        if supplier and invoice.invoice_date:
            window_start = invoice.invoice_date - timedelta(days=90)
            result = await self.db.execute(
                select(PurchaseOrder).where(
                    and_(
                        PurchaseOrder.client_id == client_id,
                        PurchaseOrder.supplier_id == supplier.id,
                        PurchaseOrder.issued_date >= window_start,
                        PurchaseOrder.issued_date <= invoice.invoice_date,
                        PurchaseOrder.status.in_(["issued", "partially_received"]),
                    )
                )
            )
            candidates = result.scalars().all()

            # Score candidates by total amount proximity
            best_po = None
            best_diff = Decimal("9999999")
            for po in candidates:
                po_total = sum(ln.line_total for ln in po.lines)
                diff = abs(po_total - invoice.grand_total)
                if diff < best_diff:
                    best_diff = diff
                    best_po = po

            # Accept if total is within 10% (covers partial invoices and rounding)
            if best_po and invoice.grand_total > 0:
                pct_diff = best_diff / invoice.grand_total
                if pct_diff <= Decimal("0.10"):
                    return best_po

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Step 3 — Supplier match validation
    # ──────────────────────────────────────────────────────────────────────────

    async def _suppliers_match(self, invoice: Invoice, po: PurchaseOrder) -> bool:
        # If both have resolved supplier IDs, compare directly
        if invoice.supplier_id and po.supplier_id:
            return invoice.supplier_id == po.supplier_id

        # Fall back to name fuzzy match
        score = fuzz.token_set_ratio(
            invoice.supplier_name_raw.lower(), po.supplier_name.lower()
        )
        return score >= 80

    # ──────────────────────────────────────────────────────────────────────────
    # Step 4 — GRN lookup
    # ──────────────────────────────────────────────────────────────────────────

    async def _find_grn(self, po: PurchaseOrder, invoice_date: date | None) -> GoodsReceiptNote | None:
        query = select(GoodsReceiptNote).where(GoodsReceiptNote.po_id == po.id)
        if invoice_date:
            query = query.where(GoodsReceiptNote.received_date <= invoice_date)
        query = query.order_by(GoodsReceiptNote.received_date.desc())

        result = await self.db.execute(query)
        return result.scalars().first()

    # ──────────────────────────────────────────────────────────────────────────
    # Step 5 — Line-level matching
    # ──────────────────────────────────────────────────────────────────────────

    async def _match_lines(
        self, invoice: Invoice, po: PurchaseOrder, grn: GoodsReceiptNote | None
    ) -> list[LineMatchDecision]:
        decisions = []
        price_tol = self.config.price_tolerance_pct
        qty_tol = self.config.qty_tolerance_pct

        for inv_line in invoice.lines:
            # Find best matching PO line
            po_line = self._find_best_po_line(inv_line, po.lines)

            # Find corresponding GRN line
            grn_line = None
            if grn and po_line:
                grn_line = next(
                    (gl for gl in grn.lines if gl.po_line_id == po_line.id), None
                )

            decision = self._evaluate_line(inv_line, po_line, grn_line, price_tol, qty_tol)
            decisions.append(decision)

        return decisions

    def _find_best_po_line(
        self, inv_line: InvoiceLine, po_lines: list[PurchaseOrderLine]
    ) -> PurchaseOrderLine | None:
        if not po_lines:
            return None

        best_score = 0
        best_line = None

        for po_line in po_lines:
            # Score by description similarity
            desc_score = fuzz.token_set_ratio(
                inv_line.description.lower(), po_line.description.lower()
            )
            # Bonus for part number match
            if inv_line.po_line_ref and po_line.part_number:
                if inv_line.po_line_ref.lower() == po_line.part_number.lower():
                    desc_score = min(100, desc_score + 20)

            if desc_score > best_score:
                best_score = desc_score
                best_line = po_line

        return best_line if best_score >= 60 else None

    def _evaluate_line(
        self,
        inv_line: InvoiceLine,
        po_line: PurchaseOrderLine | None,
        grn_line: GoodsReceiptLine | None,
        price_tol: Decimal,
        qty_tol: Decimal,
    ) -> LineMatchDecision:
        zero = Decimal("0")

        if po_line is None:
            return LineMatchDecision(
                invoice_line=inv_line,
                po_line=None,
                grn_line=None,
                status=LineMatchStatus.not_on_po,
                price_variance=zero,
                price_variance_pct=zero,
                qty_variance=zero,
                financial_exposure=inv_line.line_total,
                reason="Invoice line has no matching line on the purchase order",
            )

        # Price variance
        price_var = inv_line.unit_price - po_line.unit_price
        price_var_pct = abs(price_var / po_line.unit_price) if po_line.unit_price else zero

        # Quantity analysis
        grn_qty = grn_line.quantity_received if grn_line else None
        inv_qty = inv_line.quantity
        po_qty = po_line.quantity

        qty_var = zero
        qty_status = LineMatchStatus.matched

        if grn_qty is not None:
            qty_var = inv_qty - grn_qty
            if qty_var > qty_tol * po_qty:
                qty_status = LineMatchStatus.qty_over  # paying for undelivered
            elif qty_var < -qty_tol * po_qty:
                qty_status = LineMatchStatus.qty_under  # partial invoice
        else:
            # No GRN — compare invoice qty against PO qty
            qty_var = inv_qty - po_qty
            if qty_var > qty_tol * po_qty:
                qty_status = LineMatchStatus.qty_over

        # Price status
        if price_var_pct > price_tol:
            price_status = LineMatchStatus.price_over if price_var > 0 else LineMatchStatus.price_under
        else:
            price_status = LineMatchStatus.matched

        # Determine final line status (qty issues take priority over price issues)
        if qty_status != LineMatchStatus.matched:
            final_status = qty_status
        elif price_status != LineMatchStatus.matched:
            final_status = price_status
        else:
            final_status = LineMatchStatus.matched

        # Financial exposure = overcharge amount
        financial_exposure = max(zero, price_var * inv_qty)
        if qty_status == LineMatchStatus.qty_over and grn_qty is not None:
            financial_exposure += (inv_qty - grn_qty) * inv_line.unit_price

        reason = self._line_reason(final_status, price_var, price_var_pct, qty_var, grn_qty)

        return LineMatchDecision(
            invoice_line=inv_line,
            po_line=po_line,
            grn_line=grn_line,
            status=final_status,
            price_variance=price_var,
            price_variance_pct=price_var_pct,
            qty_variance=qty_var,
            financial_exposure=financial_exposure,
            reason=reason,
        )

    def _line_reason(
        self,
        status: LineMatchStatus,
        price_var: Decimal,
        price_var_pct: Decimal,
        qty_var: Decimal,
        grn_qty,
    ) -> str:
        pct = float(price_var_pct) * 100
        if status == LineMatchStatus.matched:
            return "Line matched within tolerance"
        if status == LineMatchStatus.price_over:
            return f"Invoice unit price is {pct:.2f}% above PO price (£{price_var:+.4f}/unit)"
        if status == LineMatchStatus.price_under:
            return f"Invoice unit price is {pct:.2f}% below PO price (£{price_var:+.4f}/unit)"
        if status == LineMatchStatus.qty_over:
            return f"Invoice quantity exceeds goods received by {qty_var} units — paying for undelivered goods"
        if status == LineMatchStatus.qty_under:
            return f"Invoice quantity {qty_var} below goods received — partial invoice"
        if status == LineMatchStatus.not_on_po:
            return "Line item not found on purchase order"
        if status == LineMatchStatus.not_received:
            return "Line item on PO but no goods receipt found"
        return "Unknown"

    # ──────────────────────────────────────────────────────────────────────────
    # Step 6 — Overall status
    # ──────────────────────────────────────────────────────────────────────────

    def _determine_status(
        self, line_decisions: list[LineMatchDecision], grn: GoodsReceiptNote | None
    ) -> MatchStatus:
        if not line_decisions:
            return MatchStatus.no_po_found

        if grn is None:
            return MatchStatus.no_grn_found

        statuses = {ld.status for ld in line_decisions}
        price_variances = [ld.price_variance_pct for ld in line_decisions]
        major_threshold = Decimal("0.05")

        if LineMatchStatus.qty_over in statuses:
            return MatchStatus.qty_discrepancy

        if LineMatchStatus.not_on_po in statuses:
            return MatchStatus.price_discrepancy

        if any(v > major_threshold for v in price_variances):
            return MatchStatus.price_discrepancy

        if LineMatchStatus.price_over in statuses or LineMatchStatus.price_under in statuses:
            return MatchStatus.partial_match

        return MatchStatus.full_match

    # ──────────────────────────────────────────────────────────────────────────
    # Step 7 — Match score
    # ──────────────────────────────────────────────────────────────────────────

    def _calculate_score(
        self, line_decisions: list[LineMatchDecision], status: MatchStatus
    ) -> Decimal:
        if not line_decisions:
            return Decimal("0")

        matched = sum(1 for ld in line_decisions if ld.status == LineMatchStatus.matched)
        total = len(line_decisions)
        base_score = Decimal(str(matched / total))

        penalty_map = {
            MatchStatus.full_match: Decimal("0"),
            MatchStatus.partial_match: Decimal("0.10"),
            MatchStatus.price_discrepancy: Decimal("0.25"),
            MatchStatus.qty_discrepancy: Decimal("0.35"),
            MatchStatus.supplier_mismatch: Decimal("0.50"),
            MatchStatus.no_grn_found: Decimal("0.40"),
            MatchStatus.no_po_found: Decimal("1.00"),
            MatchStatus.manual_override: Decimal("0"),
        }

        score = max(Decimal("0"), base_score - penalty_map.get(status, Decimal("0")))
        return score.quantize(Decimal("0.0001"))

    # ──────────────────────────────────────────────────────────────────────────
    # Step 8 — Auto-approval evaluation
    # ──────────────────────────────────────────────────────────────────────────

    def _evaluate_auto_approval(
        self,
        invoice: Invoice,
        status: MatchStatus,
        line_decisions: list[LineMatchDecision],
        discrepancy_total: Decimal,
    ) -> tuple[bool, list[str]]:
        blocks = []

        if not self.config.auto_approve_enabled:
            blocks.append("Auto-approval is disabled for this client")

        if self.config.auto_approve_requires_full_match and status != MatchStatus.full_match:
            blocks.append(f"Match status is '{status}' — full match required for auto-approval")

        if invoice.grand_total > self.config.auto_approve_limit_gbp:
            blocks.append(
                f"Invoice total £{invoice.grand_total} exceeds auto-approval limit "
                f"£{self.config.auto_approve_limit_gbp}"
            )

        if invoice.fraud_flags:
            blocks.append(f"Fraud flags present: {', '.join(invoice.fraud_flags)}")

        if invoice.extraction_confidence and invoice.extraction_confidence < self.config.extraction_confidence_threshold:
            blocks.append(
                f"AI extraction confidence {float(invoice.extraction_confidence):.0%} below threshold "
                f"{float(self.config.extraction_confidence_threshold):.0%}"
            )

        return len(blocks) == 0, blocks


async def run_match_and_save(
    db: AsyncSession,
    invoice: Invoice,
    config: ClientConfig,
) -> MatchResult:
    """Run the matching engine and persist the result to the database."""
    engine = MatchingEngine(db, config)
    decision = await engine.match(invoice)

    match_result = MatchResult(
        client_id=invoice.client_id,
        invoice_id=invoice.id,
        po_id=decision.po.id if decision.po else None,
        grn_id=decision.grn.id if decision.grn else None,
        status=decision.status,
        match_score=decision.score,
        matched_by=MatchedBy.auto,
        discrepancy_total=decision.discrepancy_total,
        exception_reason=(
            "; ".join(decision.auto_approve_block_reasons)
            if not decision.can_auto_approve else None
        ),
    )
    db.add(match_result)
    await db.flush()  # get match_result.id

    for ld in decision.line_decisions:
        line_result = MatchLineResult(
            match_result_id=match_result.id,
            invoice_line_id=ld.invoice_line.id,
            po_line_id=ld.po_line.id if ld.po_line else None,
            grn_line_id=ld.grn_line.id if ld.grn_line else None,
            status=ld.status,
            po_unit_price=ld.po_line.unit_price if ld.po_line else None,
            invoice_unit_price=ld.invoice_line.unit_price,
            price_variance=ld.price_variance,
            price_variance_pct=ld.price_variance_pct,
            po_quantity=ld.po_line.quantity if ld.po_line else None,
            grn_quantity=ld.grn_line.quantity_received if ld.grn_line else None,
            invoice_quantity=ld.invoice_line.quantity,
            qty_variance=ld.qty_variance,
            financial_exposure=ld.financial_exposure,
        )
        db.add(line_result)

    # Update invoice status
    invoice.status = "matched" if decision.status not in [
        MatchStatus.no_po_found, MatchStatus.no_grn_found, MatchStatus.supplier_mismatch
    ] else "exception"

    await db.flush()
    return match_result
