"""S-74: parental_consents — COPPA/GDPR-K consent workflow.

Revision ID: 0033_s74_parental_consent
Revises: 0032_s73_async_tracing
Create Date: 2026-11-06

Токен согласия хранится только SHA-256-хэшем; исходный токен уходит
родителю (dev — консольный email) и возвращается только в dev-ответе.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_s74_parental_consent"
down_revision: str | None = "0032_s73_async_tracing"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parental_consents",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), primary_key=True
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("parent_email", sa.String(length=255), nullable=False),
        sa.Column("policy_version", sa.String(length=16), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'granted', 'revoked', 'expired')",
            name="status_values",
        ),
    )
    op.create_index(
        "ix_parental_consents_user_status",
        "parental_consents",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_parental_consents_expires", "parental_consents", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_parental_consents_expires", table_name="parental_consents"
    )
    op.drop_index(
        "ix_parental_consents_user_status", table_name="parental_consents"
    )
    op.drop_table("parental_consents")
