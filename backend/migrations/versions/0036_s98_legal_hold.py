"""S-98: legal_holds - удержание данных субъекта до отзыва.

Revision ID: 0036_s98_legal_hold
Revises: 0035_s83_email_outbox
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_s98_legal_hold"
down_revision: str | None = "0035_s83_email_outbox"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legal_holds",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), primary_key=True
        ),
        sa.Column(
            "subject_type",
            sa.String(length=32),
            nullable=False,
            server_default="user",
        ),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_legal_holds_subject", "legal_holds", ["subject_type", "subject_id"]
    )
    op.create_index("ix_legal_holds_expires", "legal_holds", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_legal_holds_expires", table_name="legal_holds")
    op.drop_index("ix_legal_holds_subject", table_name="legal_holds")
    op.drop_table("legal_holds")
