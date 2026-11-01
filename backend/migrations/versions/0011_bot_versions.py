"""S-17: bot_versions — версии кода ботов (Design §11.2, ADR-007).

Revision ID: 0011_bot_versions
Revises: 0010_skill_scores
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_bot_versions"
down_revision: str | None = "0010_skill_scores"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("entry", sa.String(length=64), nullable=False, server_default="choose_move"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_bot_versions_user", "bot_versions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_bot_versions_user", table_name="bot_versions")
    op.drop_table("bot_versions")
