"""S-48: async-турниры — progress/job/cancel, ходы и replay.

Revision ID: 0023_tournament_v2
Revises: 0022_observability
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_tournament_v2"
down_revision: str | None = "0022_observability"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("progress", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "tournaments",
        sa.Column(
            "total_matches", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column("tournaments", sa.Column("job_id", sa.String(length=64), nullable=True))
    op.add_column(
        "tournaments",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("tournaments", sa.Column("error", sa.Text(), nullable=True))
    op.execute(
        "ALTER TABLE tournaments DROP CONSTRAINT "
        "ck_tournaments_ck_tournaments_tournament_status_values"
    )
    op.execute(
        "ALTER TABLE tournaments ADD CONSTRAINT "
        "ck_tournaments_ck_tournaments_tournament_status_values "
        "CHECK (status IN ('draft', 'queued', 'running', 'done', 'cancelled', 'failed'))"
    )

    op.create_table(
        "tournament_moves",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("match_id", sa.BigInteger(), nullable=False),
        sa.Column("bot_version_id", sa.BigInteger(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("fen", sa.Text(), nullable=False),
        sa.Column("uci", sa.String(length=8), nullable=False),
        sa.Column("agent", sa.String(length=8), nullable=False),
        sa.Column("think_ms", sa.Integer(), nullable=False),
        sa.Column("sf_sample", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["match_id"], ["tournament_matches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["bot_version_id"], ["bot_versions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_tournament_moves_match", "tournament_moves", ["match_id"])
    op.create_index(
        "ix_tournament_moves_tournament", "tournament_moves", ["tournament_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_tournament_moves_tournament", table_name="tournament_moves")
    op.drop_index("ix_tournament_moves_match", table_name="tournament_moves")
    op.drop_table("tournament_moves")
    op.execute(
        "ALTER TABLE tournaments DROP CONSTRAINT "
        "ck_tournaments_ck_tournaments_tournament_status_values"
    )
    op.execute(
        "ALTER TABLE tournaments ADD CONSTRAINT "
        "ck_tournaments_ck_tournaments_tournament_status_values "
        "CHECK (status IN ('draft', 'running', 'done'))"
    )
    op.drop_column("tournaments", "error")
    op.drop_column("tournaments", "cancel_requested")
    op.drop_column("tournaments", "job_id")
    op.drop_column("tournaments", "total_matches")
    op.drop_column("tournaments", "progress")
