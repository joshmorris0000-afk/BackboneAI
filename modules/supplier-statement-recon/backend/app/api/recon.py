"""
Supplier Statement Reconciliation API endpoints.

All endpoints require JWT authentication. client_id comes from the token.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.models.recon_data import (
    LedgerLine,
    MatchStatus,
    ReconDiscrepancy,
    ReconSession,
    ReconciliationStatus,
    StatementLine,
)
from app.models.shared import User, UserRole
from app.services import audit

router = APIRouter(prefix="/statement-recon", tags=["statement-recon"])


# ─── Reconciliation Sessions ──────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    supplier_id: uuid.UUID
    statement_date: str       # YYYY-MM-DD
    period_from: str          # YYYY-MM-DD
    period_to: str            # YYYY-MM-DD
    statement_total: float
    currency: str = "GBP"
    raw_statement_text: Optional[str] = None


@router.post("/sessions", status_code=201)
async def create_session(
    body: CreateSessionRequest,
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date
    session = ReconSession(
        client_id=current_user.client_id,
        supplier_id=body.supplier_id,
        statement_date=date.fromisoformat(body.statement_date),
        period_from=date.fromisoformat(body.period_from),
        period_to=date.fromisoformat(body.period_to),
        statement_total=Decimal(str(body.statement_total)),
        statement_currency=body.currency,
        raw_statement_text=body.raw_statement_text,
        created_by=current_user.id,
        status=ReconciliationStatus.pending.value,
    )
    db.add(session)
    await db.flush()

    await audit.log(
        db, action="recon_session_created", entity_type="recon_session",
        entity_id=session.id, client_id=current_user.client_id,
        actor_type="user", actor_id=current_user.id,
        detail={"supplier_id": str(body.supplier_id), "statement_total": body.statement_total},
    )

    return {"id": session.id, "status": session.status}


@router.get("/sessions")
async def list_sessions(
    supplier_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(ReconSession)
        .where(ReconSession.client_id == current_user.client_id)
        .order_by(desc(ReconSession.created_at))
        .limit(limit)
    )
    if supplier_id:
        query = query.where(ReconSession.supplier_id == supplier_id)
    if status_filter:
        query = query.where(ReconSession.status == status_filter)

    sessions = (await db.execute(query)).scalars().all()
    return [_session_summary(s) for s in sessions]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(ReconSession, session_id)
    if not session or session.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_detail(session)


def _session_summary(s: ReconSession) -> dict:
    return {
        "id": s.id,
        "supplier_id": s.supplier_id,
        "statement_date": s.statement_date.isoformat(),
        "period_from": s.period_from.isoformat(),
        "period_to": s.period_to.isoformat(),
        "statement_total": float(s.statement_total),
        "ledger_total": float(s.ledger_total) if s.ledger_total is not None else None,
        "variance": float(s.variance) if s.variance is not None else None,
        "status": s.status,
        "matched_count": s.matched_count,
        "discrepancy_count": s.discrepancy_count,
        "total_discrepancy_value": float(s.total_discrepancy_value) if s.total_discrepancy_value else None,
        "created_at": s.created_at,
    }


def _session_detail(s: ReconSession) -> dict:
    d = _session_summary(s)
    d["ai_summary"] = s.ai_summary
    d["reviewed_by"] = s.reviewed_by
    d["reviewed_at"] = s.reviewed_at
    return d


# ─── Statement Lines ──────────────────────────────────────────────────────────

class StatementLineIn(BaseModel):
    supplier_reference: str
    our_reference: Optional[str] = None
    transaction_date: str
    due_date: Optional[str] = None
    amount: float
    description: Optional[str] = None
    transaction_type: str = "invoice"


@router.post("/sessions/{session_id}/statement-lines", status_code=201)
async def add_statement_lines(
    session_id: uuid.UUID,
    lines: List[StatementLineIn],
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as date_type
    session = await db.get(ReconSession, session_id)
    if not session or session.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status not in (ReconciliationStatus.pending.value, ReconciliationStatus.in_progress.value):
        raise HTTPException(status_code=422, detail="Cannot add lines to a completed session")

    created = []
    for l in lines:
        stmt = StatementLine(
            session_id=session_id,
            client_id=current_user.client_id,
            supplier_id=session.supplier_id,
            supplier_reference=l.supplier_reference,
            our_reference=l.our_reference,
            transaction_date=date_type.fromisoformat(l.transaction_date),
            due_date=date_type.fromisoformat(l.due_date) if l.due_date else None,
            amount=Decimal(str(l.amount)),
            description=l.description,
            transaction_type=l.transaction_type,
        )
        db.add(stmt)
        created.append(stmt)

    await db.flush()
    return {"added": len(created)}


# ─── Ledger Lines ─────────────────────────────────────────────────────────────

class LedgerLineIn(BaseModel):
    our_reference: str
    supplier_reference: Optional[str] = None
    transaction_date: str
    due_date: Optional[str] = None
    amount: float
    description: Optional[str] = None
    transaction_type: str = "invoice"
    erp_id: Optional[str] = None


@router.post("/sessions/{session_id}/ledger-lines", status_code=201)
async def add_ledger_lines(
    session_id: uuid.UUID,
    lines: List[LedgerLineIn],
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as date_type
    session = await db.get(ReconSession, session_id)
    if not session or session.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status not in (ReconciliationStatus.pending.value, ReconciliationStatus.in_progress.value):
        raise HTTPException(status_code=422, detail="Cannot add lines to a completed session")

    created = []
    for l in lines:
        ledger = LedgerLine(
            session_id=session_id,
            client_id=current_user.client_id,
            supplier_id=session.supplier_id,
            our_reference=l.our_reference,
            supplier_reference=l.supplier_reference,
            transaction_date=date_type.fromisoformat(l.transaction_date),
            due_date=date_type.fromisoformat(l.due_date) if l.due_date else None,
            amount=Decimal(str(l.amount)),
            description=l.description,
            transaction_type=l.transaction_type,
            erp_id=l.erp_id,
        )
        db.add(ledger)
        created.append(ledger)

    await db.flush()
    return {"added": len(created)}


# ─── PDF/Text Statement Import ────────────────────────────────────────────────

@router.post("/sessions/{session_id}/import-statement")
async def import_statement_from_text(
    session_id: uuid.UUID,
    body: dict,  # {"raw_text": "..."}
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
    db: AsyncSession = Depends(get_db),
):
    """
    Parse raw statement text (from PDF extraction, email, or paste) using Claude.
    Automatically creates StatementLine records for the session.
    """
    from datetime import date as date_type
    from app.services.statement_parser import extract_statement_lines_from_text, parse_statement_line

    session = await db.get(ReconSession, session_id)
    if not session or session.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Session not found")

    raw_text = body.get("raw_text", "").strip()
    if not raw_text:
        raise HTTPException(status_code=422, detail="raw_text is required")

    try:
        extracted = await extract_statement_lines_from_text(raw_text)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse statement: {str(e)}")

    created = 0
    errors = []
    for raw_line in extracted:
        try:
            parsed = parse_statement_line(raw_line)
        except ValueError as e:
            errors.append(str(e))
            continue

        stmt = StatementLine(
            session_id=session_id,
            client_id=current_user.client_id,
            supplier_id=session.supplier_id,
            **parsed,
        )
        db.add(stmt)
        created += 1

    await db.flush()

    # Save raw text for audit trail
    if not session.raw_statement_text:
        session.raw_statement_text = raw_text
        await db.flush()

    return {"lines_created": created, "parse_errors": errors}


# ─── Run Reconciliation ───────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/run")
async def run_reconciliation(
    session_id: uuid.UUID,
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
    db: AsyncSession = Depends(get_db),
):
    """
    Run the matching engine against all loaded statement and ledger lines.
    Updates the session with results and creates discrepancy records.
    """
    from sqlalchemy.orm import selectinload
    from app.services.reconciler import ReconciliationEngine
    from app.core.config import get_settings

    cfg = get_settings()

    result = await db.execute(
        select(ReconSession)
        .options(
            selectinload(ReconSession.statement_lines),
            selectinload(ReconSession.ledger_lines),
        )
        .where(ReconSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session or session.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == ReconciliationStatus.closed.value:
        raise HTTPException(status_code=422, detail="Cannot re-run a closed session")

    if not session.statement_lines:
        raise HTTPException(status_code=422, detail="No statement lines loaded — import statement first")

    session.status = ReconciliationStatus.in_progress.value
    await db.flush()

    engine = ReconciliationEngine(
        db=db,
        amount_tolerance=Decimal(str(cfg.amount_tolerance_gbp)),
        date_tolerance_days=cfg.date_tolerance_days,
        reference_fuzzy_threshold=cfg.reference_fuzzy_threshold,
    )
    await engine.run(session)

    await audit.log(
        db, action="recon_run_completed", entity_type="recon_session",
        entity_id=session_id, client_id=current_user.client_id,
        actor_type="user", actor_id=current_user.id,
        detail={
            "matched": session.matched_count,
            "discrepancies": session.discrepancy_count,
            "variance": float(session.variance or 0),
        },
    )

    return {
        "status": session.status,
        "matched_count": session.matched_count,
        "discrepancy_count": session.discrepancy_count,
        "total_discrepancy_value": float(session.total_discrepancy_value or 0),
        "variance": float(session.variance or 0),
        "ai_summary": session.ai_summary,
    }


# ─── Discrepancies ────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/discrepancies")
async def list_discrepancies(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(ReconSession, session_id)
    if not session or session.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(ReconDiscrepancy)
        .where(ReconDiscrepancy.session_id == session_id)
        .order_by(desc(ReconDiscrepancy.financial_impact))
    )
    discs = result.scalars().all()

    return [
        {
            "id": d.id,
            "discrepancy_type": d.discrepancy_type,
            "status": d.status,
            "financial_impact": float(d.financial_impact),
            "ai_explanation": d.ai_explanation,
            "statement_line_id": d.statement_line_id,
            "ledger_line_id": d.ledger_line_id,
            "resolved_at": d.resolved_at,
            "resolution_notes": d.resolution_notes,
        }
        for d in discs
    ]


class ResolveDiscrepancyRequest(BaseModel):
    resolution: str  # resolved | disputed
    notes: str


@router.post("/discrepancies/{discrepancy_id}/resolve")
async def resolve_discrepancy(
    discrepancy_id: uuid.UUID,
    body: ResolveDiscrepancyRequest,
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
    db: AsyncSession = Depends(get_db),
):
    disc = await db.get(ReconDiscrepancy, discrepancy_id)
    if not disc or disc.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Discrepancy not found")

    if body.resolution not in ("resolved", "disputed"):
        raise HTTPException(status_code=422, detail="resolution must be 'resolved' or 'disputed'")

    disc.status = body.resolution
    disc.resolution_notes = body.notes
    disc.resolved_by = current_user.id
    disc.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    await audit.log(
        db, action=f"discrepancy_{body.resolution}", entity_type="recon_discrepancy",
        entity_id=discrepancy_id, client_id=current_user.client_id,
        actor_type="user", actor_id=current_user.id,
        detail={"notes": body.notes, "financial_impact": float(disc.financial_impact)},
    )

    return {"status": disc.status, "resolved_at": disc.resolved_at}


# ─── Summary ──────────────────────────────────────────────────────────────────

@router.get("/summary")
async def recon_summary(
    supplier_id: Optional[uuid.UUID] = None,
    days: int = Query(default=90, ge=30, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta
    from sqlalchemy import func

    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    client_id = current_user.client_id

    query = select(
        func.count(ReconSession.id),
        func.sum(ReconSession.discrepancy_count),
        func.sum(ReconSession.total_discrepancy_value),
        func.avg(ReconSession.variance),
    ).where(
        and_(
            ReconSession.client_id == client_id,
            ReconSession.statement_date >= since,
        )
    )

    if supplier_id:
        query = query.where(ReconSession.supplier_id == supplier_id)

    result = await db.execute(query)
    row = result.one()

    open_result = await db.execute(
        select(func.count(ReconDiscrepancy.id)).where(
            and_(
                ReconDiscrepancy.client_id == client_id,
                ReconDiscrepancy.status.notin_(["resolved", "disputed"]),
            )
        )
    )

    return {
        "period_days": days,
        "sessions_reconciled": row[0] or 0,
        "total_discrepancies_found": row[1] or 0,
        "total_discrepancy_value_gbp": round(float(row[2] or 0), 2),
        "avg_variance_gbp": round(float(row[3] or 0), 2),
        "open_discrepancies": open_result.scalar() or 0,
    }
