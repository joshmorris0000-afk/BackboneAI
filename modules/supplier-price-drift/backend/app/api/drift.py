"""
Supplier Price Drift API endpoints.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.price_data import AlertStatus, ContractedPrice, DriftAlert, PriceObservation

router = APIRouter(prefix="/price-drift", tags=["price-drift"])


# ─── Contracted Prices ────────────────────────────────────────────────────────

class ContractedPriceIn(BaseModel):
    supplier_id: uuid.UUID
    description: str
    sku: str | None = None
    unit_price: float
    uom: str = "each"
    valid_from: str  # YYYY-MM-DD
    valid_to: str | None = None
    tolerance_pct: float | None = None
    notes: str | None = None


@router.post("/contracted-prices", status_code=201)
async def create_contracted_price(
    client_id: uuid.UUID,
    body: ContractedPriceIn,
    db: AsyncSession = Depends(get_db),
):
    import re
    from decimal import Decimal
    from datetime import date

    cp = ContractedPrice(
        client_id=client_id,
        supplier_id=body.supplier_id,
        sku=body.sku,
        description=body.description,
        description_normalised=re.sub(r"\s+", " ", body.description.lower().strip()),
        unit_price=Decimal(str(body.unit_price)),
        uom=body.uom,
        valid_from=date.fromisoformat(body.valid_from),
        valid_to=date.fromisoformat(body.valid_to) if body.valid_to else None,
        tolerance_pct=Decimal(str(body.tolerance_pct)) if body.tolerance_pct else None,
        notes=body.notes,
    )
    db.add(cp)
    await db.flush()
    return {"id": cp.id, "description": cp.description, "unit_price": float(cp.unit_price)}


@router.get("/contracted-prices")
async def list_contracted_prices(
    client_id: uuid.UUID,
    supplier_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ContractedPrice).where(ContractedPrice.client_id == client_id)
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
            "uom": cp.uom,
            "valid_from": cp.valid_from.isoformat(),
            "valid_to": cp.valid_to.isoformat() if cp.valid_to else None,
            "tolerance_pct": float(cp.tolerance_pct) if cp.tolerance_pct else None,
        }
        for cp in results
    ]


# ─── Alerts ───────────────────────────────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    client_id: uuid.UUID,
    status: str | None = None,
    severity: str | None = None,
    supplier_id: uuid.UUID | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(DriftAlert)
        .where(DriftAlert.client_id == client_id)
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
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(DriftAlert, alert_id)
    if not alert:
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
            "invoice_date": obs.invoice_date,
            "description": obs.description_raw,
            "sku": obs.sku,
            "observed_unit_price": float(obs.observed_unit_price),
            "contracted_unit_price": float(obs.contracted_unit_price) if obs.contracted_unit_price else None,
            "price_variance": float(obs.price_variance) if obs.price_variance else None,
            "price_variance_pct": float(obs.price_variance_pct) if obs.price_variance_pct else None,
            "financial_impact": float(obs.financial_impact) if obs.financial_impact else None,
            "quantity": float(obs.quantity),
        } if obs else None,
        "created_at": alert.created_at,
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
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(DriftAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    valid_transitions = {
        AlertStatus.open: [AlertStatus.acknowledged, AlertStatus.resolved, AlertStatus.disputed],
        AlertStatus.acknowledged: [AlertStatus.resolved, AlertStatus.disputed],
    }
    current = AlertStatus(alert.status)
    target = AlertStatus(body.resolution)
    if target not in valid_transitions.get(current, []):
        raise HTTPException(status_code=422, detail=f"Cannot transition from {current} to {target}")

    alert.status = target
    alert.resolution_notes = body.notes
    if target in (AlertStatus.resolved, AlertStatus.disputed):
        alert.resolved_at = datetime.now(UTC)

    return {"status": alert.status, "resolved_at": alert.resolved_at}


# ─── Summary / Trend ──────────────────────────────────────────────────────────

@router.get("/summary")
async def drift_summary(
    client_id: uuid.UUID,
    days: int = Query(default=90, ge=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta
    from sqlalchemy import func

    since = datetime.now(UTC).date() - timedelta(days=days)

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
    row = obs_result.one()

    alert_result = await db.execute(
        select(func.count(DriftAlert.id)).where(
            and_(
                DriftAlert.client_id == client_id,
                DriftAlert.created_at >= datetime.now(UTC).replace(hour=0, minute=0) - __import__('datetime').timedelta(days=days),
                DriftAlert.status == AlertStatus.open,
            )
        )
    )

    return {
        "period_days": days,
        "observations_with_drift": row[0] or 0,
        "total_financial_impact_gbp": round(float(row[1] or 0), 2),
        "avg_variance_pct": round(float(row[2] or 0), 2),
        "open_alerts": (await alert_result).scalar() or 0,
    }
