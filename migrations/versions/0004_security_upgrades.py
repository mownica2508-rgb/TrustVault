"""Add grant expiry, file versions, and tamper-evident audit checkpoints."""

import hashlib
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0004_security_upgrades"
down_revision = "0003_add_sharing_and_audit"
branch_labels = None
depends_on = None

GENESIS_HASH = hashlib.sha256(b"trustvault:audit-chain:v1").hexdigest()


def upgrade() -> None:
    op.add_column("document_permissions", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("audit_events", sa.Column("previous_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_events", sa.Column("event_hash", sa.String(length=64), nullable=True))
    op.create_index("uq_audit_event_hash", "audit_events", ["event_hash"], unique=True)

    op.create_table(
        "audit_chain_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.Integer(), nullable=True),
        sa.Column("last_hash", sa.String(length=64), nullable=False),
        sa.Column("legacy_through_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("legacy_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    legacy = op.get_bind().execute(sa.text("SELECT COALESCE(MAX(id), 0), COUNT(*) FROM audit_events")).one()
    op.get_bind().execute(
        sa.text(
            "INSERT INTO audit_chain_state (id, last_event_id, last_hash, legacy_through_id, legacy_event_count) "
            "VALUES (1, NULL, :hash, :legacy_through_id, :legacy_event_count)"
        ),
        {
            "hash": GENESIS_HASH,
            "legacy_through_id": int(legacy[0]),
            "legacy_event_count": int(legacy[1]),
        },
    )

    versions = op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_name", sa.String(length=80), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])

    # Existing files become version 1 so owners retain history across the upgrade.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, owner_id, original_filename, storage_name, content_type, size_bytes, sha256, created_at FROM documents")
    ).mappings().all()
    for row in rows:
        created_at = row["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        connection.execute(
            versions.insert().values(
                document_id=row["id"],
                version_number=1,
                original_filename=row["original_filename"],
                storage_name=row["storage_name"],
                content_type=row["content_type"],
                size_bytes=row["size_bytes"],
                sha256=row["sha256"],
                uploaded_by_id=row["owner_id"],
                created_at=created_at,
            )
        )


def downgrade() -> None:
    op.drop_index("ix_document_versions_document_id", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_table("audit_chain_state")
    op.drop_index("uq_audit_event_hash", table_name="audit_events")
    op.drop_column("audit_events", "event_hash")
    op.drop_column("audit_events", "previous_hash")
    op.drop_column("document_permissions", "expires_at")
