"""
ERP Sync Scheduler.

Runs background jobs to pull POs, GRNs, and suppliers from client ERPs
on a fixed schedule. All token refresh is handled silently within each connector.

Schedule:
  - Purchase Orders: every 15 minutes
  - Goods Receipts:  every 15 minutes
  - Suppliers:       every 60 minutes

The scheduler starts on application startup and runs for the lifetime of the process.
"""
import logging
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.client import Client, ConnectorCredential
from app.models.documents import GoodsReceiptLine, GoodsReceiptNote, PurchaseOrder, PurchaseOrderLine
from app.models.supplier import Supplier

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


async def start_scheduler():
    _scheduler.add_job(sync_all_pos, "interval", minutes=15, id="sync_pos")
    _scheduler.add_job(sync_all_grns, "interval", minutes=15, id="sync_grns")
    _scheduler.add_job(sync_all_suppliers, "interval", minutes=60, id="sync_suppliers")
    _scheduler.start()
    logger.info("ERP sync scheduler started")


def _get_connector(credential: ConnectorCredential, db):
    from app.services.connectors.sage200 import Sage200CloudConnector
    from app.services.connectors.xero import XeroConnector

    mapping = {
        "sage200": Sage200CloudConnector,
        "xero": XeroConnector,
    }
    cls = mapping.get(credential.connector_type)
    if cls:
        return cls(credential, db)
    return None


async def sync_all_pos():
    async with AsyncSessionLocal() as db:
        credentials = (
            await db.execute(
                select(ConnectorCredential).where(ConnectorCredential.is_active == True)
            )
        ).scalars().all()

        for cred in credentials:
            if cred.connector_type not in ("sage200", "xero"):
                continue
            connector = _get_connector(cred, db)
            if not connector:
                continue

            try:
                pos = await connector.fetch_purchase_orders(since=cred.last_sync_at)
                for erp_po in pos:
                    await _upsert_po(db, cred.client_id, erp_po)
                await db.commit()
                logger.info(f"Synced {len(pos)} POs for client {cred.client_id}")
            except Exception as e:
                await connector.record_error(str(e))
                await db.commit()
                logger.error(f"PO sync failed for client {cred.client_id}: {e}")


async def sync_all_grns():
    async with AsyncSessionLocal() as db:
        credentials = (
            await db.execute(
                select(ConnectorCredential).where(ConnectorCredential.is_active == True)
            )
        ).scalars().all()

        for cred in credentials:
            connector = _get_connector(cred, db)
            if not connector:
                continue

            try:
                grns = await connector.fetch_goods_receipts(since=cred.last_sync_at)
                for erp_grn in grns:
                    await _upsert_grn(db, cred.client_id, erp_grn)
                await db.commit()
                logger.info(f"Synced {len(grns)} GRNs for client {cred.client_id}")
            except Exception as e:
                await connector.record_error(str(e))
                await db.commit()
                logger.error(f"GRN sync failed for client {cred.client_id}: {e}")


async def sync_all_suppliers():
    async with AsyncSessionLocal() as db:
        credentials = (
            await db.execute(
                select(ConnectorCredential).where(ConnectorCredential.is_active == True)
            )
        ).scalars().all()

        for cred in credentials:
            connector = _get_connector(cred, db)
            if not connector:
                continue

            try:
                suppliers = await connector.fetch_suppliers()
                for erp_supplier in suppliers:
                    await _upsert_supplier(db, cred.client_id, erp_supplier)
                await db.commit()
            except Exception as e:
                await connector.record_error(str(e))
                await db.commit()
                logger.error(f"Supplier sync failed for client {cred.client_id}: {e}")


async def _upsert_po(db, client_id: uuid.UUID, erp_po):
    from app.models.documents import DocumentSource

    existing = (
        await db.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.client_id == client_id,
                PurchaseOrder.po_number == erp_po.po_number,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.status = erp_po.status
        existing.expected_delivery = erp_po.expected_delivery
    else:
        po = PurchaseOrder(
            client_id=client_id,
            po_number=erp_po.po_number,
            supplier_name=erp_po.supplier_name,
            issued_date=erp_po.issued_date,
            expected_delivery=erp_po.expected_delivery,
            currency=erp_po.currency,
            status=erp_po.status,
            source=erp_po.source_ref and "sage200" or "xero",
            source_ref=erp_po.source_ref,
        )
        db.add(po)
        await db.flush()

        for erp_line in erp_po.lines:
            line = PurchaseOrderLine(
                purchase_order_id=po.id,
                line_number=erp_line.line_number,
                description=erp_line.description,
                part_number=erp_line.part_number,
                quantity=erp_line.quantity,
                unit_price=erp_line.unit_price,
                vat_rate=erp_line.vat_rate,
                uom=erp_line.uom,
                line_total=erp_line.quantity * erp_line.unit_price,
            )
            db.add(line)


async def _upsert_grn(db, client_id: uuid.UUID, erp_grn):
    existing = (
        await db.execute(
            select(GoodsReceiptNote).where(
                GoodsReceiptNote.client_id == client_id,
                GoodsReceiptNote.grn_number == erp_grn.grn_number,
            )
        )
    ).scalar_one_or_none()

    if existing:
        return  # GRNs are immutable once received

    # Link to PO
    po = (
        await db.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.client_id == client_id,
                PurchaseOrder.po_number == erp_grn.po_number,
            )
        )
    ).scalar_one_or_none()

    grn = GoodsReceiptNote(
        client_id=client_id,
        grn_number=erp_grn.grn_number,
        po_id=po.id if po else None,
        received_date=erp_grn.received_date,
        received_by=erp_grn.received_by,
        source=erp_grn.source_ref and "sage200" or "xero",
        source_ref=erp_grn.source_ref,
    )
    db.add(grn)
    await db.flush()

    for erp_line in erp_grn.lines:
        line = GoodsReceiptLine(
            grn_id=grn.id,
            description=erp_line.description,
            part_number=erp_line.part_number,
            quantity_ordered=erp_line.quantity_ordered,
            quantity_received=erp_line.quantity_received,
            quantity_rejected=erp_line.quantity_rejected,
            rejection_reason=erp_line.rejection_reason,
            uom=erp_line.uom,
        )
        db.add(line)


async def _upsert_supplier(db, client_id: uuid.UUID, erp_supplier):
    existing = (
        await db.execute(
            select(Supplier).where(
                Supplier.client_id == client_id,
                Supplier.canonical_name.ilike(erp_supplier.name),
            )
        )
    ).scalar_one_or_none()

    if existing:
        if erp_supplier.vat_number:
            existing.vat_number = erp_supplier.vat_number
    else:
        supplier = Supplier(
            client_id=client_id,
            canonical_name=erp_supplier.name,
            vat_number=erp_supplier.vat_number,
            source_ref=erp_supplier.source_ref,
        )
        db.add(supplier)
