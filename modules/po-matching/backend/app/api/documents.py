"""
Document endpoints — upload invoices, list POs, list GRNs.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.database import get_db
from app.models.client import ClientConfig
from app.models.documents import Invoice, InvoiceLine, InvoiceStatus
from app.models.user import User, UserRole
from app.services.ai_extractor import extract_invoice
from app.services.matcher import run_match_and_save

router = APIRouter(tags=["documents"])


@router.post("/invoices/upload", status_code=202)
async def upload_invoice(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.ap_manager, UserRole.ap_reviewer])),
):
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="Only PDF files are accepted")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    # AI extraction
    try:
        extraction = await extract_invoice(pdf_bytes, str(current_user.client_id))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Duplicate check
    existing = (
        await db.execute(
            select(Invoice).where(
                Invoice.client_id == current_user.client_id,
                Invoice.invoice_number == extraction.invoice_number,
                Invoice.supplier_name_raw.ilike(extraction.supplier_name),
            )
        )
    ).scalar_one_or_none()

    # Build invoice record
    invoice = Invoice(
        client_id=current_user.client_id,
        invoice_number=extraction.invoice_number,
        supplier_name_raw=extraction.supplier_name,
        supplier_vat_number=extraction.supplier_vat_number,
        invoice_date=extraction.invoice_date,
        due_date=extraction.due_date,
        po_reference_raw=extraction.po_reference,
        currency=extraction.currency,
        subtotal=extraction.subtotal,
        vat_total=extraction.vat_total,
        grand_total=extraction.grand_total,
        payment_terms=extraction.payment_terms,
        source="upload",
        extraction_confidence=Decimal(str(extraction.overall_confidence)),
        extraction_model="claude-sonnet-4-6",
        extraction_raw=extraction.raw_response,
        fraud_flags=extraction.fraud_flags or None,
        status=InvoiceStatus.extracted,
        is_duplicate=existing is not None,
    )
    db.add(invoice)
    await db.flush()

    for extracted_line in extraction.lines:
        line = InvoiceLine(
            invoice_id=invoice.id,
            description=extracted_line.description,
            quantity=extracted_line.quantity,
            unit_price=extracted_line.unit_price,
            vat_rate=extracted_line.vat_rate,
            line_total=extracted_line.line_total,
        )
        db.add(line)

    await db.flush()

    # Run matching immediately if not a duplicate and no fraud flags
    if not invoice.is_duplicate and not invoice.fraud_flags:
        config = (
            await db.execute(
                select(ClientConfig).where(ClientConfig.client_id == current_user.client_id)
            )
        ).scalar_one_or_none()

        if config:
            match_result = await run_match_and_save(db, invoice, config)
            return {
                "invoice_id": invoice.id,
                "status": invoice.status,
                "match_id": match_result.id,
                "match_status": match_result.status,
                "extraction_confidence": float(invoice.extraction_confidence or 0),
                "fraud_flags": invoice.fraud_flags or [],
                "is_duplicate": invoice.is_duplicate,
            }

    return {
        "invoice_id": invoice.id,
        "status": invoice.status,
        "match_id": None,
        "extraction_confidence": float(invoice.extraction_confidence or 0),
        "fraud_flags": invoice.fraud_flags or [],
        "is_duplicate": invoice.is_duplicate,
        "message": "Invoice held for review — duplicate detected or fraud flags present" if invoice.is_duplicate or invoice.fraud_flags else None,
    }


@router.get("/invoices")
async def list_invoices(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(Invoice)
        .where(Invoice.client_id == current_user.client_id)
        .order_by(Invoice.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        query = query.where(Invoice.status == status)

    invoices = (await db.execute(query)).scalars().all()
    return [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "supplier_name": inv.supplier_name_raw,
            "grand_total": float(inv.grand_total),
            "invoice_date": inv.invoice_date,
            "status": inv.status,
            "is_duplicate": inv.is_duplicate,
            "fraud_flags": inv.fraud_flags or [],
            "extraction_confidence": float(inv.extraction_confidence or 0),
        }
        for inv in invoices
    ]


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.client_id != current_user.client_id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "supplier_name": invoice.supplier_name_raw,
        "supplier_vat_number": invoice.supplier_vat_number,
        "invoice_date": invoice.invoice_date,
        "due_date": invoice.due_date,
        "po_reference": invoice.po_reference_raw,
        "currency": invoice.currency,
        "subtotal": float(invoice.subtotal),
        "vat_total": float(invoice.vat_total),
        "grand_total": float(invoice.grand_total),
        "payment_terms": invoice.payment_terms,
        "status": invoice.status,
        "is_duplicate": invoice.is_duplicate,
        "fraud_flags": invoice.fraud_flags or [],
        "extraction_confidence": float(invoice.extraction_confidence or 0),
        "lines": [
            {
                "description": ln.description,
                "quantity": float(ln.quantity),
                "unit_price": float(ln.unit_price),
                "vat_rate": float(ln.vat_rate),
                "line_total": float(ln.line_total),
            }
            for ln in invoice.lines
        ],
    }
