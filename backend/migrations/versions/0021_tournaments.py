"""S-45: турниры ботов + LMS-экспорт.

Revision ID: 0021_tournaments
Revises: 0020_voice
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_tournaments"
down_revision: str | None = "0020_voice"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tournaments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False, server_default="bracket"),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "format IN ('bracket', 'round_robin')",
            name="ck_tournaments_tournament_format_values",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'running', 'done')",
            name="ck_tournaments_tournament_status_values",
        ),
    )

    op.create_table(
        "tournament_participants",
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("bot_version_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("losses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("draws", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("points", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint(
            "tournament_id", "bot_version_id", name="pk_tournament_participants"
        ),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bot_version_id"], ["bot_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "tournament_matches",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("match_no", sa.Integer(), nullable=False),
        sa.Column("bot_a_id", sa.BigInteger(), nullable=False),
        sa.Column("bot_b_id", sa.BigInteger(), nullable=False),
        sa.Column("winner_id", sa.BigInteger(), nullable=True),
        sa.Column("result", sa.String(length=8), nullable=False),
        sa.Column("moves_count", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bot_a_id"], ["bot_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bot_b_id"], ["bot_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["winner_id"], ["bot_versions.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("tournament_matches")
    op.drop_table("tournament_participants")
    op.drop_table("tournaments")
