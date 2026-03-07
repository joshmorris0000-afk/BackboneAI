"""
Xero Connector — OAuth 2.0.

Xero's offline_access scope provides a refresh token with 60-day validity.
The connector refreshes the access token silently every 25 minutes.
No user is ever prompted to re-authenticate.

Xero also supports webhooks for real-time PO updates. These supplement
the polling sync to reduce latency for time-sensitive matches.
"""
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
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

XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_API_BASE = "https://api.xero.com/api.xro/2.0"


class XeroConnector(BaseConnector):
    connector_type = "xero"

    async def _refresh_access_token(self):
        refresh_token = self._refresh_token()
        if not refresh_token:
            raise ConnectorAuthError("Xero: no refresh token stored — re-authorisation required")

        http = await self._get_http()
        response = await http.post(
            XERO_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(settings.xero_client_id, settings.xero_client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code in (400, 401):
            raise ConnectorAuthError(
                "Xero: refresh token rejected. This may mean the user has disconnected the app "
                "in Xero. Backbone AI ops team notified."
            )

        response.raise_for_status()
        data = response.json()

        await self._save_tokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in", 1800),
        )

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
    )
    async def _get(self, path: str, params: dict | None = None) -> dict:
        await self.ensure_authenticated()
        http = await self._get_http()
        response = await http.get(
            f"{XERO_API_BASE}/{path}",
            params=params,
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Xero-Tenant-Id": self.credential.tenant_id or "",
                "Accept": "application/json",
            },
        )
        response.raise_for_status()
        return response.json()

    async def fetch_purchase_orders(self, since: datetime | None = None) -> list[ERPPurchaseOrder]:
        params = {"Status": "AUTHORISED,BILLED,PARTIALLY_PAID"}
        if since:
            params["ModifiedAfter"] = since.strftime("%Y-%m-%dT%H:%M:%S")

        data = await self._get("PurchaseOrders", params=params)
        orders = []

        for po in data.get("PurchaseOrders", []):
            lines = [
                ERPPurchaseOrderLine(
                    line_number=i + 1,
                    description=ln.get("Description", ""),
                    quantity=Decimal(str(ln.get("Quantity", 0))),
                    unit_price=Decimal(str(ln.get("UnitAmount", 0))),
                    vat_rate=self._tax_rate_to_decimal(ln.get("TaxType", "OUTPUT2")),
                    uom=ln.get("UnitOfMeasure", "each"),
                    part_number=ln.get("ItemCode"),
                )
                for i, ln in enumerate(po.get("LineItems", []))
            ]
            orders.append(
                ERPPurchaseOrder(
                    po_number=po.get("PurchaseOrderNumber", ""),
                    supplier_name=po.get("Contact", {}).get("Name", ""),
                    supplier_ref=po.get("Contact", {}).get("ContactID", ""),
                    issued_date=self._parse_xero_date(po.get("DateString")),
                    expected_delivery=self._parse_xero_date(po.get("DeliveryDateString")),
                    currency=po.get("CurrencyCode", "GBP"),
                    status=po.get("Status", "").lower(),
                    source_ref=po["PurchaseOrderID"],
                    lines=lines,
                )
            )

        await self.update_sync_timestamp()
        return orders

    async def fetch_goods_receipts(self, since: datetime | None = None) -> list[ERPGoodsReceipt]:
        # Xero does not have a native GRN object in standard API.
        # GRNs are tracked via inventory adjustments or custom tracking.
        # For clients with Xero, GRNs are imported via CSV until a custom
        # inventory module is configured.
        return []

    async def fetch_suppliers(self) -> list[ERPSupplier]:
        data = await self._get("Contacts", params={"where": "IsSupplier=true AND IsArchived=false"})
        return [
            ERPSupplier(
                name=c.get("Name", ""),
                source_ref=c["ContactID"],
                vat_number=c.get("TaxNumber"),
            )
            for c in data.get("Contacts", [])
        ]

    @staticmethod
    def _parse_xero_date(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("T00:00:00", "")).date()
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _tax_rate_to_decimal(tax_type: str) -> Decimal:
        """Map Xero tax type codes to decimal rates."""
        mapping = {
            "OUTPUT2": Decimal("0.20"),
            "OUTPUT": Decimal("0.20"),
            "ZERORATEDOUTPUT": Decimal("0.00"),
            "EXEMPTOUTPUT": Decimal("0.00"),
            "REDUCEDOUTPUT": Decimal("0.05"),
        }
        return mapping.get(tax_type, Decimal("0.20"))
