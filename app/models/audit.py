from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditEvent(Base):
    """Append-only application event. No API exposes update or delete operations."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_created_action", "created_at", "action"),
        Index("ix_audit_document_id", "document_id"),
        Index("uq_audit_event_hash", "event_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # No FK: retain the document ID for a deletion event after its row is removed.
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    outcome: Mapped[str] = mapped_column(String(12), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AuditChainState(Base):
    """The latest HMAC checkpoint; a DB-only editor cannot forge new events."""

    __tablename__ = "audit_chain_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_through_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    legacy_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
