"""Add document grants and append-only activity events."""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_sharing_and_audit"
down_revision = "0002_create_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("granted_by_id", sa.Integer(), nullable=False),
        sa.Column("access_level", sa.Enum("read", "edit", name="accesslevel", native_enum=False, length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_permissions_recipient_active", "document_permissions", ["recipient_id", "revoked_at"])
    op.create_index("ix_permissions_document_active", "document_permissions", ["document_id", "revoked_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("outcome", sa.String(length=12), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_document_id", "audit_events", ["document_id"])
    op.create_index("ix_audit_created_action", "audit_events", ["created_at", "action"])


def downgrade() -> None:
    op.drop_index("ix_audit_created_action", table_name="audit_events")
    op.drop_index("ix_audit_document_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_permissions_document_active", table_name="document_permissions")
    op.drop_index("ix_permissions_recipient_active", table_name="document_permissions")
    op.drop_table("document_permissions")
