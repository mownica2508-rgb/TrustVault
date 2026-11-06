import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AccessLevel(str, enum.Enum):
    READ = "read"
    EDIT = "edit"


class DocumentPermission(Base):
    """A grant history row. Revocation timestamps preserve the audit history."""

    __tablename__ = "document_permissions"
    __table_args__ = (
        Index("ix_permissions_recipient_active", "recipient_id", "revoked_at"),
        Index("ix_permissions_document_active", "document_id", "revoked_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    granted_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    access_level: Mapped[AccessLevel] = mapped_column(
        Enum(
            AccessLevel,
            native_enum=False,
            length=10,
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="permissions")
    recipient = relationship("User", foreign_keys=[recipient_id])
    granted_by = relationship("User", foreign_keys=[granted_by_id])
