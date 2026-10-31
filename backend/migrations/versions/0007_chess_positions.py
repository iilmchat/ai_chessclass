"""S-11: chess_positions — позиции ученика с последними фактами (Design §6.3).

meta хранит: факты SF (линии/материал), текст LLM-объяснения и уровень
объяснения. UpSet по паре (user_id, fen) — одна запись на позицию.

Revision ID: 0007_chess_positions
Revises: 0006_py_hints_cognitive
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_chess_positions"
down_revision: str | None = "0006_py_hints_cognitive"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chess_positions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("fen", sa.String(length=128), nullable=False),
        sa.Column(
            "meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_chess_positions_user_fen", "chess_positions", ["user_id", "fen"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_chess_positions_user_fen", table_name="chess_positions")
    op.drop_table("chess_positions")
