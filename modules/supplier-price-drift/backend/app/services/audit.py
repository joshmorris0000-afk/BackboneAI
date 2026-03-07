from __future__ import annotations

"""
Audit logging service — write-only. Every call appends a new immutable record.
"""
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    actor_type: str = "system",
    actor_id: uuid.UUID | None = None,
    actor_ip: str | None = None,
    detail: dict[str, Any] | None = None,
    notes: str | None = None,
) -> None:
    """Append an immutable audit record. Never raises — log failures are swallowed
    so that a logging error never breaks the business operation being audited."""
    from app.core.security import hash_ip

    try:
        entry = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            client_id=client_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_ip_hash=hash_ip(actor_ip) if actor_ip else None,
            detail=detail,
            notes=notes,
        )
        db.add(entry)
        await db.flush()
    except Exception:
        pass  # audit failure must never surface to caller
