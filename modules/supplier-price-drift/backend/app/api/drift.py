from __future__ import annotations

"""
Supplier Price Drift API endpoints.

All endpoints require a valid JWT. client_id is extracted from the token — no
client can query another client's data by manipulating URL parameters.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.price_data import AlertStatus, ContractedPrice, DriftAlert, PriceObservation
from app.models.user import User, UserRole
from app.services import audit

router = APIRouter(prefix="/price-drift", tags=["price-drift"])


# ─── Contracted Prices ────────────────────────────────────────────────────────

class ContractedPriceIn(BaseModel):
    supplier_id: uuid.UUID
    description: str
    sku: str | None = None
    unit_price: float
    uom: str = "each"
    currency: str = "GBP"
    valid_from: str  # YYYY-MM-DD
    valid_to: str | None = None
    tolerance_pct: float | None = None
    notes: str | None = None


@router.post("/contracted-prices", status_code=201)
async def create_contracted_price(
    body: ContractedPriceIn,
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager])),
    db: AsyncSession = Depends(get_db),
):
    import re
    from datetime import date

    cp = ContractedPrice(
        client_id=current_user.client_id,
        supplier_id=body.supplier_id,
        sku=body.sku,
        description=body.description,
        description_normalised=re.sub(r"\s+", " ", body.description.lower().strip()),
        unit_price=Decimal(str(body.unit_price)),
        currency=body.currency,
        uom=body.uom,
        valid_from=date.fromisoformat(body.valid_from),
        valid_to=date.fromisoformat(body.valid_to) if body.valid_to else None,
        tolerance_pct=Decimal(str(body.tolerance_pct)) if body.tolerance_pct else None,
        notes=body.notes,
    )
    db.add(cp)
    await db.flush()

    await audit.log(
        db,
        action="contracted_price_created",
        entity_type="contracted_price",
        entity_id=cp.id,
        client_id=current_user.client_id,
        actor_type="user",
        actor_id=current_user.id,
        detail={
            "supplier_id": str(body.supplier_id),
            "description": body.description,
            "unit_price": body.unit_price,
            "sku": body.sku,
            "valid_from": body.valid_from,
        },
    )

    return {"id": cp.id, "description": cp.description, "unit_price": float(cp.unit_price)}


@router.get("/contracted-prices")
async def list_contracted_prices(
    supplier_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ContractedPrice).where(ContractedPrice.client_id == current_user.client_id)
    if supplier_id:
        query = query.where(ContractedPrice.supplier_id == supplier_id)
    results = (await db.execute(query)).scalars().all()
    return [
        {
            "id": cp.id,
            "supplier_id": cp.supplier_id,
            "sku": cp.sku,
            "description": cp.description,
            "unit_price": float(cp.unit_price),
            "currency": cp.currency,
            "uom": cp.uom,
            "valid_from": cp.valid_from.isoformat(),
            "valid_to": cp.valid_to.isoformat() if cp.valid_to else None,
            "tolerance_pct": float(cp.tolerance_pct) if cp.tolerance_pct else None,
            "notes": cp.notes,
        }
        for cp in results
    ]


@router.delete("/contracted-prices/{price_id}", status_code=204)
async def delete_contracted_price(
    price_id: uuid.UUID,
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager])),
    db: AsyncSession = Depends(get_db),
):
    cp = await db.get(ContractedPrice, price_id)
    if not cp or cp.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Contracted price not found")

    await audit.log(
        db,
        action="contracted_price_deleted",
        entity_type="contracted_price",
        entity_id=price_id,
        client_id=current_user.client_id,
        actor_type="user",
        actor_id=current_user.id,
        detail={"description": cp.description, "unit_price": float(cp.unit_price)},
    )

    await db.delete(cp)


# ─── Alerts ───────────────────────────────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    supplier_id: uuid.UUID | None = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(DriftAlert)
        .where(DriftAlert.client_id == current_user.client_id)
        .order_by(desc(DriftAlert.created_at))
        .limit(limit)
    )
    if status:
        query = query.where(DriftAlert.status == status)
    if severity:
        query = query.where(DriftAlert.severity == severity)
    if supplier_id:
        query = query.where(DriftAlert.supplier_id == supplier_id)

    alerts = (await db.execute(query)).scalars().all()

    return [
        {
            "id": a.id,
            "supplier_id": a.supplier_id,
            "severity": a.severity,
            "direction": a.direction,
            "status": a.status,
            "total_drift_this_month": float(a.total_drift_this_month),
            "occurrences_this_month": a.occurrences_this_month,
            "ai_summary": a.ai_summary,
            "created_at": a.created_at,
        }
        for a in alerts
    ]


@router.get("/alerts/{alert_id}")
async def get_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(DriftAlert, alert_id)
    if not alert or alert.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Alert not found")

    obs = await db.get(PriceObservation, alert.observation_id)

    return {
        "id": alert.id,
        "severity": alert.severity,
        "direction": alert.direction,
        "status": alert.status,
        "ai_summary": alert.ai_summary,
        "total_drift_this_month": float(alert.total_drift_this_month),
        "occurrences_this_month": alert.occurrences_this_month,
        "observation": {
            "invoice_number": obs.invoice_number,
            "invoice_date": obs.invoice_date.isoformat(),
            "description": obs.description_raw,
            "sku": obs.sku,
            "observed_unit_price": float(obs.observed_unit_price),
            "contracted_unit_price": float(obs.contracted_unit_price) if obs.contracted_unit_price else None,
            "price_variance": float(obs.price_variance) if obs.price_variance else None,
            "price_variance_pct": float(obs.price_variance_pct) if obs.price_variance_pct else None,
            "financial_impact": float(obs.financial_impact) if obs.financial_impact else None,
            "quantity": float(obs.quantity),
            "currency": obs.currency,
        } if obs else None,
        "created_at": alert.created_at,
        "resolved_by": alert.resolved_by,
        "resolved_at": alert.resolved_at,
        "resolution_notes": alert.resolution_notes,
    }


class ResolveRequest(BaseModel):
    resolution: str  # acknowledged | resolved | disputed
    notes: str


@router.post("/alerts/{alert_id}/resolve", status_code=200)
async def resolve_alert(
    alert_id: uuid.UUID,
    body: ResolveRequest,
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(DriftAlert, alert_id)
    if not alert or alert.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Alert not found")

    valid_transitions = {
        AlertStatus.open: [AlertStatus.acknowledged, AlertStatus.resolved, AlertStatus.disputed],
        AlertStatus.acknowledged: [AlertStatus.resolved, AlertStatus.disputed],
    }
    current_status = AlertStatus(alert.status)

    try:
        target = AlertStatus(body.resolution)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid resolution value: '{body.resolution}'")

    if target not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=422,
            detail=f"Cannot transition from '{current_status}' to '{target}'",
        )

    alert.status = target.value
    alert.resolution_notes = body.notes
    alert.resolved_by = current_user.id
    if target in (AlertStatus.resolved, AlertStatus.disputed):
        alert.resolved_at = datetime.now(timezone.utc)

    await db.flush()

    await audit.log(
        db,
        action=f"alert_{target.value}",
        entity_type="drift_alert",
        entity_id=alert_id,
        client_id=current_user.client_id,
        actor_type="user",
        actor_id=current_user.id,
        detail={"previous_status": current_status.value, "new_status": target.value, "notes": body.notes},
    )

    return {
        "status": alert.status,
        "resolved_by": str(current_user.id),
        "resolved_at": alert.resolved_at,
    }


# ─── Summary / Trend ──────────────────────────────────────────────────────────

@router.get("/summary")
async def drift_summary(
    days: int = Query(default=90, ge=30, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    client_id = current_user.client_id

    obs_result = await db.execute(
        select(
            func.count(PriceObservation.id),
            func.sum(PriceObservation.financial_impact),
            func.avg(PriceObservation.price_variance_pct),
        ).where(
            and_(
                PriceObservation.client_id == client_id,
                PriceObservation.invoice_date >= since,
                PriceObservation.financial_impact > 0,
            )
        )
    )
    obs_row = obs_result.one()

    alert_result = await db.execute(
        select(func.count(DriftAlert.id)).where(
            and_(
                DriftAlert.client_id == client_id,
                DriftAlert.created_at >= datetime.now(timezone.utc) - timedelta(days=days),
                DriftAlert.status == AlertStatus.open.value,
            )
        )
    )
    open_count = alert_result.scalar() or 0

    # Breakdown by severity for open alerts in the period
    severity_result = await db.execute(
        select(DriftAlert.severity, func.count(DriftAlert.id)).where(
            and_(
                DriftAlert.client_id == client_id,
                DriftAlert.created_at >= datetime.now(timezone.utc) - timedelta(days=days),
            )
        ).group_by(DriftAlert.severity)
    )
    severity_counts = {row[0]: row[1] for row in severity_result.all()}

    return {
        "period_days": days,
        "since": since.isoformat(),
        "observations_with_positive_drift": obs_row[0] or 0,
        "total_financial_impact_gbp": round(float(obs_row[1] or 0), 2),
        "avg_variance_pct": round(float(obs_row[2] or 0), 2),
        "open_alerts": open_count,
        "alerts_by_severity": severity_counts,
    }


# ─── Invoice line processing (internal / integration endpoint) ─────────────────

class InvoiceLineIn(BaseModel):
    invoice_id: str
    invoice_number: str
    invoice_date: str  # YYYY-MM-DD
    supplier_id: str
    description: str
    sku: str | None = None
    unit_price: float
    quantity: float
    currency: str = "GBP"


@router.post("/process-lines")
async def process_invoice_lines_endpoint(
    lines: list[InvoiceLineIn],
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
    db: AsyncSession = Depends(get_db),
):
    """
    Process a batch of invoice lines through the drift detector.
    Called automatically by the PO Matching module (Module 01) when an invoice
    is processed, or can be called directly for standalone testing.
    """
    from datetime import date
    from app.services.drift_detector import DriftDetector, InvoiceLine
    from app.models.client import Client

    client = await db.get(Client, current_user.client_id)
    tolerance = client.drift_tolerance_pct or Decimal("0.02")

    detector = DriftDetector(db=db, client_default_tolerance=tolerance)

    invoice_lines = [
        InvoiceLine(
            invoice_id=l.invoice_id,
            invoice_number=l.invoice_number,
            invoice_date=date.fromisoformat(l.invoice_date),
            supplier_id=l.supplier_id,
            client_id=str(current_user.client_id),
            description=l.description,
            sku=l.sku,
            unit_price=Decimal(str(l.unit_price)),
            quantity=Decimal(str(l.quantity)),
            currency=l.currency,
        )
        for l in lines
    ]

    results = []
    for line in invoice_lines:
        result = await detector.process_line(line)
        results.append({
            "observation_id": result.observation_id,
            "alert_id": result.alert_id,
            "severity": result.severity.value if result.severity else None,
            "direction": result.direction.value if result.direction else None,
            "contracted_price": float(result.contracted_price) if result.contracted_price else None,
            "observed_price": float(result.observed_price),
            "variance_pct": result.variance_pct,
            "financial_impact": float(result.financial_impact) if result.financial_impact else None,
            "ai_summary": result.ai_summary,
        })

    await audit.log(
        db,
        action="invoice_lines_processed",
        client_id=current_user.client_id,
        actor_type="user",
        actor_id=current_user.id,
        detail={
            "line_count": len(lines),
            "alerts_raised": sum(1 for r in results if r["alert_id"]),
        },
    )

    return results
