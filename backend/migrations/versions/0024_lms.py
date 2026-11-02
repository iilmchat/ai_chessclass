"""S-49: lrs_deliveries — идемпотентная доставка xAPI в LRS.

Revision ID: 0024_lms
Revises: 0023_tournament_v2
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_lms"
down_revision: str | None = "0023_tournament_v2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lrs_deliveries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("statement_id", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("statement_id", name="uq_lrs_deliveries_statement_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name="ck_lrs_deliveries_lrs_delivery_status_values",
        ),
    )
    op.create_index("ix_lrs_deliveries_status", "lrs_deliveries", ["status"])


def downgrade() -> None:
    op.drop_index("ix_lrs_deliveries_status", table_name="lrs_deliveries")
    op.drop_table("lrs_deliveries")
