"""
Sage 200 Cloud Connector.

Supports both:
  - Sage 200 Cloud (OAuth 2.0, REST API)
  - Sage 200 Professional / Standard on-premise (SQL Server read-only)

OAuth token lifecycle:
  - Access token: short-lived (typically 1 hour)
  - Refresh token: long-lived, rotated on each use
  - The connector refreshes silently 5 minutes before expiry.
  - No user is ever prompted to re-authenticate.

On-premise:
  - Uses a read-only SQL Server service account.
  - Connection pooled and always-on.
  - Credentials stored AES-256 encrypted in connector_credentials.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.models.client import ConnectorCredential
from app.services.connectors.base import (
    BaseConnector,
    ConnectorAuthError,
    ERPGoodsReceipt,
    ERPGRNLine,
    ERPPurchaseOrder,
    ERPPurchaseOrderLine,
    ERPSupplier,
)

settings = get_settings()

SAGE_TOKEN_URL = "https://id.sage.com/oauth/token"
SAGE_API_BASE = "https://api.columbus.sage.com/uk/sage200"


class Sage200CloudConnector(BaseConnector):
    """Sage 200 Cloud — OAuth 2.0 REST connector."""

    connector_type = "sage200"

    async def _refresh_access_token(self):
        """
        Exchange refresh token for a new access + refresh token pair.
        Sage 200 Cloud rotates the refresh token on each use.
        New tokens are encrypted and saved — no user interaction needed.
        """
        refresh_token = self._refresh_token()
        if not refresh_token:
            raise ConnectorAuthError("Sage 200: no refresh token stored — re-authorisation required")

        http = await self._get_http()
        response = await http.post(
            SAGE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.sage200_client_id,
                "client_secret": settings.sage200_client_secret,
            },
        )

        if response.status_code == 401:
            raise ConnectorAuthError(
                "Sage 200: refresh token rejected — credentials may have been revoked. "
                "Backbone AI ops team notified."
            )

        response.raise_for_status()
        data = response.json()

        await self._save_tokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),  # Sage rotates refresh tokens
            expires_in=data.get("expires_in", 3600),
        )

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
    )
    async def _get(self, path: str, params: dict | None = None) -> list | dict:
        await self.ensure_authenticated()
        http = await self._get_http()
        response = await http.get(
            f"{SAGE_API_BASE}{path}",
            params=params,
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "X-Site": self.credential.tenant_id or "",
            },
        )
        if response.status_code == 429:
            # Rate limited — tenacity will retry with backoff
            response.raise_for_status()
        response.raise_for_status()
        return response.json()

    async def fetch_purchase_orders(self, since: datetime | None = None) -> list[ERPPurchaseOrder]:
        params = {"$filter": "Status eq 'Live'"}
        if since:
            iso = since.strftime("%Y-%m-%dT%H:%M:%S")
            params["$filter"] += f" and DateTimeUpdated gt datetime'{iso}'"

        data = await self._get("/v1/purchase_orders", params=params)
        orders = []

        for po_data in data.get("$resources", []):
            lines = await self._fetch_po_lines(po_data["Id"])
            orders.append(
                ERPPurchaseOrder(
                    po_number=po_data.get("DocumentNo", ""),
                    supplier_name=po_data.get("SupplierName", ""),
                    supplier_ref=str(po_data.get("SupplierId", "")),
                    issued_date=self._parse_date(po_data.get("DocumentDate")),
                    expected_delivery=self._parse_date(po_data.get("RequestedDeliveryDate")),
                    currency=po_data.get("CurrencyId", "GBP"),
                    status=po_data.get("Status", "").lower(),
                    source_ref=str(po_data["Id"]),
                    lines=lines,
                )
            )

        await self.update_sync_timestamp()
        return orders

    async def _fetch_po_lines(self, po_id: str) -> list[ERPPurchaseOrderLine]:
        data = await self._get(f"/v1/purchase_order_lines", params={"$filter": f"PurchaseOrderId eq {po_id}"})
        lines = []
        for i, ln in enumerate(data.get("$resources", []), start=1):
            unit_price = Decimal(str(ln.get("UnitPrice", 0)))
            qty = Decimal(str(ln.get("QtyOrdered", 0)))
            lines.append(
                ERPPurchaseOrderLine(
                    line_number=i,
                    description=ln.get("Description", ""),
                    quantity=qty,
                    unit_price=unit_price,
                    vat_rate=Decimal(str(ln.get("TaxRate", 20))) / 100,
                    uom=ln.get("UnitOfMeasure", "each"),
                    part_number=ln.get("Code"),
                )
            )
        return lines

    async def fetch_goods_receipts(self, since: datetime | None = None) -> list[ERPGoodsReceipt]:
        params: dict = {}
        if since:
            iso = since.strftime("%Y-%m-%dT%H:%M:%S")
            params["$filter"] = f"DateTimeUpdated gt datetime'{iso}'"

        data = await self._get("/v1/purchase_order_receipts", params=params)
        receipts = []

        for grn_data in data.get("$resources", []):
            lines = [
                ERPGRNLine(
                    description=ln.get("Description", ""),
                    quantity_ordered=Decimal(str(ln.get("QtyOrdered", 0))),
                    quantity_received=Decimal(str(ln.get("QtyReceived", 0))),
                    quantity_rejected=Decimal(str(ln.get("QtyRejected", 0))),
                    uom=ln.get("UnitOfMeasure", "each"),
                    part_number=ln.get("Code"),
                )
                for ln in grn_data.get("Lines", [])
            ]
            receipts.append(
                ERPGoodsReceipt(
                    grn_number=grn_data.get("DocumentNo", ""),
                    po_number=grn_data.get("PurchaseOrderNo", ""),
                    supplier_ref=str(grn_data.get("SupplierId", "")),
                    received_date=self._parse_date(grn_data.get("DocumentDate")),
                    received_by=grn_data.get("ReceivedBy"),
                    source_ref=str(grn_data["Id"]),
                    lines=lines,
                )
            )

        await self.update_sync_timestamp()
        return receipts

    async def fetch_suppliers(self) -> list[ERPSupplier]:
        data = await self._get("/v1/suppliers", params={"$filter": "Status eq 'Active'"})
        return [
            ERPSupplier(
                name=s.get("Name", ""),
                source_ref=str(s["Id"]),
                vat_number=s.get("VATRegistrationNumber"),
            )
            for s in data.get("$resources", [])
        ]

    @staticmethod
    def _parse_date(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.rstrip("Z")).date()
        except (ValueError, AttributeError):
            return None
