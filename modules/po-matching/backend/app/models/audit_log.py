from typing import Optional
import uuid

from sqlalchemy import DateTime, String, Text, event, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class AuditLog(Base):
    """
    Immutable append-only audit trail. Every action in the system is recorded here.
    Postgres trigger prevents UPDATE and DELETE on this table.
    Retained for 7 years (HMRC financial record requirement).
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # invoice | po | grn | match_result | user
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    action: Mapped[str] = mapped_column(String(50), nullable=False)  # created | matched | approved | exception_raised | etc.

    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)  # system | user | api_key
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_ip_hash: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    before_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Immutable — set at insert, never changed
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# DDL: immutability trigger (applied via Alembic migration)
AUDIT_IMMUTABILITY_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is immutable — records cannot be modified or deleted';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER enforce_audit_immutability
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
"""
