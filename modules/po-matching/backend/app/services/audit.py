"""
Audit logging service. Every state change in the system writes an immutable record.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log(
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    actor_type: str = "system",
    actor_id: uuid.UUID | None = None,
    actor_ip: str | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    notes: str | None = None,
):
    """Write an immutable audit log entry."""
    from app.core.security import hash_ip

    entry = AuditLog(
        client_id=client_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_ip_hash=hash_ip(actor_ip) if actor_ip else None,
        before_state=before_state,
        after_state=after_state,
        notes=notes,
    )
    db.add(entry)
    # Don't flush here — caller controls the transaction boundary
