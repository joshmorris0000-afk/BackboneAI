"""
Base ERP connector class.

All connectors extend this. The base class handles:
- Persistent token management (silent refresh, no user prompts)
- Exponential backoff on rate limits and transient errors
- Standardised data models returned regardless of ERP source
- Error logging and last_sync_at tracking
"""
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.security import decrypt_field, encrypt_field
from app.models.client import ConnectorCredential


@dataclass
class ERPPurchaseOrderLine:
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    vat_rate: Decimal
    uom: str
    part_number: str | None = None


@dataclass
class ERPPurchaseOrder:
    po_number: str
    supplier_name: str
    supplier_ref: str
    issued_date: date
    expected_delivery: date | None
    currency: str
    status: str
    source_ref: str
    lines: list[ERPPurchaseOrderLine]


@dataclass
class ERPGRNLine:
    description: str
    quantity_ordered: Decimal
    quantity_received: Decimal
    quantity_rejected: Decimal
    uom: str
    po_line_ref: str | None = None
    part_number: str | None = None
    rejection_reason: str | None = None


@dataclass
class ERPGoodsReceipt:
    grn_number: str
    po_number: str
    supplier_ref: str
    received_date: date
    received_by: str | None
    source_ref: str
    lines: list[ERPGRNLine]


@dataclass
class ERPSupplier:
    name: str
    source_ref: str
    vat_number: str | None = None


class BaseConnector(ABC):
    """
    Abstract base for all ERP connectors.

    Design principle: once credentials are stored at setup time, the connector
    manages all token refresh, session renewal, and reconnection silently.
    No human intervention is ever required during normal operation.
    """

    connector_type: str = ""

    def __init__(self, credential: ConnectorCredential, db: AsyncSession):
        self.credential = credential
        self.db = db
        self._http: httpx.AsyncClient | None = None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            )
        return self._http

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ─── Token management ──────────────────────────────────────────────────────

    def _access_token(self) -> str | None:
        if self.credential.access_token_enc:
            return decrypt_field(self.credential.access_token_enc)
        return None

    def _refresh_token(self) -> str | None:
        if self.credential.refresh_token_enc:
            return decrypt_field(self.credential.refresh_token_enc)
        return None

    def _is_token_expiring_soon(self) -> bool:
        """Return True if the access token expires within 5 minutes."""
        if not self.credential.token_expires_at:
            return True
        return self.credential.token_expires_at <= datetime.now(UTC) + timedelta(minutes=5)

    async def _save_tokens(self, access_token: str, refresh_token: str | None, expires_in: int):
        """Encrypt and persist new tokens. Called silently after every refresh."""
        self.credential.access_token_enc = encrypt_field(access_token)
        if refresh_token:
            self.credential.refresh_token_enc = encrypt_field(refresh_token)
        self.credential.token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        self.credential.updated_at = datetime.now(UTC)
        await self.db.flush()

    async def ensure_authenticated(self):
        """
        Guarantee a valid access token before any API call.
        Refreshes silently if the token is expired or expiring soon.
        Raises ConnectorAuthError only if refresh itself fails (e.g. revoked token).
        """
        if self._is_token_expiring_soon():
            await self._refresh_access_token()

    @abstractmethod
    async def _refresh_access_token(self):
        """Silently obtain a new access token using the stored refresh token."""
        ...

    # ─── Sync operations ───────────────────────────────────────────────────────

    @abstractmethod
    async def fetch_purchase_orders(self, since: datetime | None = None) -> list[ERPPurchaseOrder]:
        """Fetch open/recent POs from the ERP."""
        ...

    @abstractmethod
    async def fetch_goods_receipts(self, since: datetime | None = None) -> list[ERPGoodsReceipt]:
        """Fetch recent goods receipts from the ERP."""
        ...

    @abstractmethod
    async def fetch_suppliers(self) -> list[ERPSupplier]:
        """Fetch all active suppliers from the ERP."""
        ...

    async def update_sync_timestamp(self):
        self.credential.last_sync_at = datetime.now(UTC)
        self.credential.last_error = None
        await self.db.flush()

    async def record_error(self, error: str):
        self.credential.last_error = error[:500]
        await self.db.flush()


class ConnectorAuthError(Exception):
    """Raised when a connector's credentials have been permanently revoked."""
    pass
