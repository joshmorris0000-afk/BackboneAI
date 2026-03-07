"""
Client model — represents a Backbone AI customer organisation.
Each client's data is fully isolated; all queries are scoped to client_id.
"""
import uuid
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Per-client drift tolerance override (if null, uses system default 2%)
    drift_tolerance_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)

    # Email to notify for alert/critical severity drift alerts
    ap_manager_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[List["User"]] = relationship(back_populates="client")
    suppliers: Mapped[List["Supplier"]] = relationship(back_populates="client")


from app.models.user import User  # noqa: E402
from app.models.supplier import Supplier  # noqa: E402
