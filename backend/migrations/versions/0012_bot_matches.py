"""S-18: bot_stats + bot_matches + bot_match_moves (Design §11.2, §7.5).

Revision ID: 0012_bot_matches
Revises: 0011_bot_versions
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_bot_matches"
down_revision: str | None = "0011_bot_versions"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_stats",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("elo", sa.Numeric(6, 1), nullable=False, server_default="1000"),
        sa.Column("wins", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("losses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("draws", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "bot_matches",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("opponent", sa.String(length=32), nullable=False),
        sa.Column("result", sa.String(length=8), nullable=False),
        sa.Column("moves_count", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("elo_delta", sa.Numeric(5, 1), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "result IN ('win', 'loss', 'draw', 'timeout', 'error')",
            name="result_values",
        ),
        sa.ForeignKeyConstraint(["version_id"], ["bot_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_bot_matches_user", "bot_matches", ["user_id"])

    op.create_table(
        "bot_match_moves",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("match_id", sa.BigInteger(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("fen", sa.Text(), nullable=False),
        sa.Column("uci", sa.String(length=8), nullable=False),
        sa.Column("agent", sa.String(length=16), nullable=False),
        sa.Column("think_ms", sa.Integer(), nullable=False),
        sa.Column("sf_sample", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["match_id"], ["bot_matches.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_bot_match_moves_match", "bot_match_moves", ["match_id"])


def downgrade() -> None:
    op.drop_index("ix_bot_match_moves_match", table_name="bot_match_moves")
    op.drop_table("bot_match_moves")
    op.drop_index("ix_bot_matches_user", table_name="bot_matches")
    op.drop_table("bot_matches")
    op.drop_table("bot_stats")
