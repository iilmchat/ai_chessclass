"""S-12: chess_games + chess_analyses (Design §11.2, §6.3).

chess_analyses.sf — результат SF по ходам (moves + blunders);
chess_analyses.llm — объяснения блюндеров (ply → content).
status: pending → running → done | failed.

Revision ID: 0008_chess_games
Revises: 0007_chess_positions
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_chess_games"
down_revision: str | None = "0007_chess_positions"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chess_games",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("pgn", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="upload"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("source IN ('upload', 'sample')", name="source_values"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chess_games_user", "chess_games", ["user_id"])

    op.create_table(
        "chess_analyses",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column(
            "sf", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "llm", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed')", name="status_values"
        ),
        sa.ForeignKeyConstraint(["game_id"], ["chess_games.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_chess_analyses_game", "chess_analyses", ["game_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_chess_analyses_game", table_name="chess_analyses")
    op.drop_table("chess_analyses")
    op.drop_index("ix_chess_games_user", table_name="chess_games")
    op.drop_table("chess_games")
