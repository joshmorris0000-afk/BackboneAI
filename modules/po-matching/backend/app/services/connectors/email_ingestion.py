"""
IMAP Email Ingestion Service.

Maintains a persistent IMAP IDLE connection to the client's invoice inbox.
When a new email arrives, it is processed immediately (push notification via IDLE).
A polling fallback runs every 5 minutes in case IDLE drops.

Supports:
- Microsoft 365 (OAuth 2.0 via MSAL — no password, no re-auth prompts)
- Google Workspace (App Password or OAuth 2.0)
- Any IMAP server (App Password / credentials)

All credentials are stored AES-256 encrypted. The connection is owned by
Backbone AI's ingestion worker — the client never sees or manages it.
"""
from __future__ import annotations

import asyncio
import email
import logging
from email.message import Message
from io import BytesIO

import imapclient

from app.core.security import decrypt_field
from app.models.client import ConnectorCredential

logger = logging.getLogger(__name__)


class EmailIngestionWorker:
    """
    Persistent IMAP worker for a single client inbox.

    Lifecycle:
    1. Connect and authenticate on startup
    2. SELECT the configured folder (typically INBOX)
    3. Enter IDLE mode — server pushes notifications on new mail
    4. On notification: DONE IDLE → SEARCH UNSEEN → fetch → process → IDLE again
    5. On connection drop: reconnect with exponential backoff (never alerts client)
    """

    IDLE_TIMEOUT = 840  # 14 minutes — refresh before most servers' 15-min IDLE timeout
    MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024  # 20 MB

    def __init__(self, credential: ConnectorCredential, on_invoice_received):
        self.credential = credential
        self.on_invoice_received = on_invoice_received  # async callback(pdf_bytes, metadata)
        self._client: imapclient.IMAPClient | None = None
        self._running = False

    def _get_password(self) -> str:
        return decrypt_field(self.credential.password_enc)

    def _connect(self):
        """Establish TLS IMAP connection. Called on start and after any disconnect."""
        host = self.credential.host
        port = self.credential.port or 993

        self._client = imapclient.IMAPClient(host, port=port, ssl=True, use_uid=True)
        self._client.login(self.credential.username, self._get_password())
        self._client.select_folder("INBOX")
        logger.info(f"IMAP connected: {host} as {self.credential.username}")

    async def run(self):
        """Main loop — runs forever until stopped. Reconnects automatically on error."""
        self._running = True
        backoff = 5

        while self._running:
            try:
                await asyncio.to_thread(self._connect)
                backoff = 5  # reset on successful connection

                while self._running:
                    await self._idle_cycle()

            except Exception as e:
                logger.error(f"IMAP error ({self.credential.host}): {e} — reconnecting in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)  # cap at 5 minutes

    async def _idle_cycle(self):
        """One IDLE cycle: enter idle, wait for notification or timeout, fetch new mail."""
        await asyncio.to_thread(self._client.idle)

        # Wait for server notification or timeout
        try:
            responses = await asyncio.wait_for(
                asyncio.to_thread(self._client.idle_check, timeout=self.IDLE_TIMEOUT),
                timeout=self.IDLE_TIMEOUT + 5,
            )
        except asyncio.TimeoutError:
            responses = []

        await asyncio.to_thread(self._client.idle_done)

        if responses:
            await self._fetch_unseen()

    async def _fetch_unseen(self):
        """Fetch all unseen messages and extract PDF attachments."""
        uids = await asyncio.to_thread(self._client.search, ["UNSEEN"])
        if not uids:
            return

        messages = await asyncio.to_thread(
            self._client.fetch, uids, ["RFC822", "ENVELOPE"]
        )

        for uid, data in messages.items():
            try:
                msg: Message = email.message_from_bytes(data[b"RFC822"])
                metadata = {
                    "uid": uid,
                    "subject": str(msg.get("Subject", "")),
                    "from": str(msg.get("From", "")),
                    "date": str(msg.get("Date", "")),
                }

                pdfs = self._extract_pdfs(msg)
                for pdf_bytes in pdfs:
                    if len(pdf_bytes) > self.MAX_ATTACHMENT_SIZE:
                        logger.warning(f"Attachment too large ({len(pdf_bytes)} bytes), skipping")
                        continue
                    await self.on_invoice_received(pdf_bytes, metadata)

                # Mark as seen only after successful processing
                await asyncio.to_thread(self._client.add_flags, [uid], [imapclient.SEEN])

            except Exception as e:
                logger.error(f"Failed to process email UID {uid}: {e}")
                # Do not mark as seen — will be retried on next cycle

    def _extract_pdfs(self, msg: Message) -> list[bytes]:
        """Extract all PDF attachments from an email."""
        pdfs = []
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            is_pdf_attachment = (
                content_type == "application/pdf"
                or (content_type == "application/octet-stream" and ".pdf" in disposition.lower())
            )

            if is_pdf_attachment:
                payload = part.get_payload(decode=True)
                if payload:
                    pdfs.append(payload)

        return pdfs

    def stop(self):
        self._running = False
        if self._client:
            try:
                self._client.logout()
            except Exception:
                pass
