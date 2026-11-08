"""Add owner-reviewed local sharing recommendations."""

from alembic import op
import sqlalchemy as sa

revision = "0005_share_suggestions"
down_revision = "0004_security_upgrades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "share_suggestions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "recipient_id", name="uq_share_suggestion_recipient"),
    )
    op.create_index("ix_share_suggestions_document_id", "share_suggestions", ["document_id"])
    op.create_index("ix_share_suggestions_recipient_id", "share_suggestions", ["recipient_id"])


def downgrade() -> None:
    op.drop_index("ix_share_suggestions_recipient_id", table_name="share_suggestions")
    op.drop_index("ix_share_suggestions_document_id", table_name="share_suggestions")
    op.drop_table("share_suggestions")
