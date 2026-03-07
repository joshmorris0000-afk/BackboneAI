"""
Matching endpoints — review queue, approve, override, reject.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.models.client import ClientConfig
from app.models.documents import Invoice
from app.models.match import MatchResult, MatchStatus
from app.models.user import User, UserRole
from app.services import audit
from app.services.matcher import run_match_and_save

router = APIRouter(prefix="/matches", tags=["matching"])


class MatchListItem(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    status: str
    match_score: float
    discrepancy_total: float
    matched_at: datetime
    invoice_number: str | None = None
    supplier_name: str | None = None


class ApproveRequest(BaseModel):
    notes: str | None = None


class OverrideRequest(BaseModel):
    reason: str
    notes: str | None = None


class RejectRequest(BaseModel):
    reason: str


@router.get("", response_model=list[MatchListItem])
async def list_matches(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(MatchResult)
        .where(MatchResult.client_id == current_user.client_id)
        .order_by(MatchResult.matched_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        query = query.where(MatchResult.status == status)

    results = (await db.execute(query)).scalars().all()

    items = []
    for r in results:
        invoice = await db.get(Invoice, r.invoice_id)
        items.append(
            MatchListItem(
                id=r.id,
                invoice_id=r.invoice_id,
                status=r.status,
                match_score=float(r.match_score),
                discrepancy_total=float(r.discrepancy_total),
                matched_at=r.matched_at,
                invoice_number=invoice.invoice_number if invoice else None,
                supplier_name=invoice.supplier_name_raw if invoice else None,
            )
        )
    return items


@router.get("/{match_id}")
async def get_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    match = await db.get(MatchResult, match_id)
    if not match or match.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Match not found")

    # Eager load related objects for full detail view
    invoice = await db.get(Invoice, match.invoice_id)

    return {
        "id": match.id,
        "status": match.status,
        "match_score": float(match.match_score),
        "discrepancy_total": float(match.discrepancy_total),
        "matched_at": match.matched_at,
        "matched_by": match.matched_by,
        "approved_at": match.approved_at,
        "exception_reason": match.exception_reason,
        "invoice": {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "supplier_name": invoice.supplier_name_raw,
            "grand_total": float(invoice.grand_total),
            "invoice_date": invoice.invoice_date,
            "fraud_flags": invoice.fraud_flags or [],
            "extraction_confidence": float(invoice.extraction_confidence or 0),
        } if invoice else None,
        "line_results": [
            {
                "id": lr.id,
                "status": lr.status,
                "invoice_line_description": lr.invoice_line.description if lr.invoice_line else None,
                "po_unit_price": float(lr.po_unit_price or 0),
                "invoice_unit_price": float(lr.invoice_unit_price or 0),
                "price_variance": float(lr.price_variance),
                "price_variance_pct": float(lr.price_variance_pct),
                "po_quantity": float(lr.po_quantity or 0),
                "grn_quantity": float(lr.grn_quantity or 0),
                "invoice_quantity": float(lr.invoice_quantity or 0),
                "qty_variance": float(lr.qty_variance),
                "financial_exposure": float(lr.financial_exposure),
            }
            for lr in match.line_results
        ],
    }


@router.post("/{match_id}/approve", status_code=200)
async def approve_match(
    match_id: uuid.UUID,
    body: ApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
):
    match = await db.get(MatchResult, match_id)
    if not match or match.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Match not found")

    if match.approved_at:
        raise HTTPException(status_code=409, detail="Match already approved")

    # Reviewer approval limit check
    if current_user.role == UserRole.ap_reviewer:
        invoice = await db.get(Invoice, match.invoice_id)
        if invoice and float(invoice.grand_total) > current_user.approval_limit_gbp:
            raise HTTPException(
                status_code=403,
                detail=f"Invoice total exceeds your approval limit of £{current_user.approval_limit_gbp:,.2f}",
            )

    before = {"approved_at": None}
    match.approved_at = datetime.now(UTC)
    match.approved_by = current_user.id
    match.reviewer_id = current_user.id

    # Update invoice status
    invoice = await db.get(Invoice, match.invoice_id)
    if invoice:
        invoice.status = "approved"

    await audit.log(
        db, action="match_approved", entity_type="match_result",
        entity_id=match.id, client_id=match.client_id,
        actor_type="user", actor_id=current_user.id, actor_ip=request.client.host,
        before_state=before,
        after_state={"approved_at": match.approved_at.isoformat(), "approved_by": str(current_user.id)},
        notes=body.notes,
    )

    return {"status": "approved", "approved_at": match.approved_at}


@router.post("/{match_id}/override", status_code=200)
async def override_match(
    match_id: uuid.UUID,
    body: OverrideRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager])),
):
    match = await db.get(MatchResult, match_id)
    if not match or match.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Match not found")

    before_status = match.status
    match.status = MatchStatus.manual_override
    match.exception_reason = body.reason
    match.approved_at = datetime.now(UTC)
    match.approved_by = current_user.id
    match.reviewer_id = current_user.id

    invoice = await db.get(Invoice, match.invoice_id)
    if invoice:
        invoice.status = "approved"

    await audit.log(
        db, action="match_overridden", entity_type="match_result",
        entity_id=match.id, client_id=match.client_id,
        actor_type="user", actor_id=current_user.id, actor_ip=request.client.host,
        before_state={"status": before_status},
        after_state={"status": MatchStatus.manual_override, "reason": body.reason},
        notes=body.notes,
    )

    return {"status": "overridden"}


@router.post("/{match_id}/reject", status_code=200)
async def reject_match(
    match_id: uuid.UUID,
    body: RejectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
):
    match = await db.get(MatchResult, match_id)
    if not match or match.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Match not found")

    match.status = "rejected"
    match.exception_reason = body.reason
    match.reviewer_id = current_user.id

    invoice = await db.get(Invoice, match.invoice_id)
    if invoice:
        invoice.status = "exception"

    await audit.log(
        db, action="match_rejected", entity_type="match_result",
        entity_id=match.id, client_id=match.client_id,
        actor_type="user", actor_id=current_user.id, actor_ip=request.client.host,
        after_state={"status": "rejected", "reason": body.reason},
    )

    return {"status": "rejected"}


@router.post("/run", status_code=202)
async def trigger_match(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager])),
):
    """Manually trigger matching for a specific invoice."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    config = (
        await db.execute(
            select(ClientConfig).where(ClientConfig.client_id == current_user.client_id)
        )
    ).scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=500, detail="Client config not found")

    match_result = await run_match_and_save(db, invoice, config)
    return {"match_id": match_result.id, "status": match_result.status}
