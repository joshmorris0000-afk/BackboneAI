"""
Reporting endpoints — financial summaries, exception reports, supplier scorecards.
"""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.documents import Invoice
from app.models.match import MatchResult, MatchStatus
from app.models.user import User

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary")
async def monthly_summary(
    days: int = Query(default=30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overall matching performance for the selected period."""
    since = datetime.now(UTC) - timedelta(days=days)
    client_id = current_user.client_id

    results = (
        await db.execute(
            select(MatchResult).where(
                MatchResult.client_id == client_id,
                MatchResult.matched_at >= since,
            )
        )
    ).scalars().all()

    total = len(results)
    if total == 0:
        return {"period_days": days, "total_invoices": 0, "match_rate": 0}

    full_matches = sum(1 for r in results if r.status == MatchStatus.full_match)
    auto_approved = sum(1 for r in results if r.approved_at and r.matched_by == "auto")
    total_discrepancy = sum(float(r.discrepancy_total) for r in results)

    return {
        "period_days": days,
        "total_invoices": total,
        "full_match_count": full_matches,
        "match_rate_pct": round(full_matches / total * 100, 1),
        "auto_approved_count": auto_approved,
        "total_discrepancy_gbp": round(total_discrepancy, 2),
        "avg_discrepancy_per_invoice_gbp": round(total_discrepancy / total, 2),
        "status_breakdown": {
            status: sum(1 for r in results if r.status == status)
            for status in [s.value for s in MatchStatus]
        },
    }


@router.get("/exceptions")
async def open_exceptions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All unresolved exceptions requiring human action."""
    exception_statuses = [
        MatchStatus.price_discrepancy,
        MatchStatus.qty_discrepancy,
        MatchStatus.supplier_mismatch,
        MatchStatus.no_po_found,
        MatchStatus.no_grn_found,
    ]

    results = (
        await db.execute(
            select(MatchResult).where(
                MatchResult.client_id == current_user.client_id,
                MatchResult.status.in_(exception_statuses),
                MatchResult.approved_at.is_(None),
            ).order_by(MatchResult.discrepancy_total.desc())
        )
    ).scalars().all()

    items = []
    for r in results:
        invoice = await db.get(Invoice, r.invoice_id)
        items.append({
            "match_id": r.id,
            "status": r.status,
            "invoice_number": invoice.invoice_number if invoice else None,
            "supplier": invoice.supplier_name_raw if invoice else None,
            "grand_total": float(invoice.grand_total) if invoice else 0,
            "discrepancy_total": float(r.discrepancy_total),
            "matched_at": r.matched_at,
            "exception_reason": r.exception_reason,
            "fraud_flags": invoice.fraud_flags if invoice else [],
        })

    return {
        "count": len(items),
        "total_exposure_gbp": round(sum(i["discrepancy_total"] for i in items), 2),
        "exceptions": items,
    }


@router.get("/financial-exposure")
async def financial_exposure(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Total £ at risk across all open discrepancies."""
    results = (
        await db.execute(
            select(MatchResult).where(
                MatchResult.client_id == current_user.client_id,
                MatchResult.approved_at.is_(None),
                MatchResult.discrepancy_total > 0,
            )
        )
    ).scalars().all()

    total_exposure = sum(float(r.discrepancy_total) for r in results)

    return {
        "open_exception_count": len(results),
        "total_exposure_gbp": round(total_exposure, 2),
        "by_status": {
            status: {
                "count": sum(1 for r in results if r.status == status),
                "exposure_gbp": round(
                    sum(float(r.discrepancy_total) for r in results if r.status == status), 2
                ),
            }
            for status in set(r.status for r in results)
        },
    }
