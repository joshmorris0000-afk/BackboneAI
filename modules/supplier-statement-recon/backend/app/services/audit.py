from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shared import AuditLog


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
        pass
