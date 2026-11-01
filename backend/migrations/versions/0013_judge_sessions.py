"""S-23: anticheat_judge_sessions — транскрипты «объясни свой код/ход».

Транскрипт хранится (§9.3); вердикт за учителем (ADR-005) — поле verdict
свободное (учитель пишет заключение после просмотра).

Revision ID: 0013_judge_sessions
Revises: 0012_bot_matches
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_judge_sessions"
down_revision: str | None = "0012_bot_matches"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anticheat_judge_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_ref", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("model_used", sa.String(length=64), nullable=False),
        sa.Column(
            "transcript", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("teacher_verdict", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_judge_sessions_user", "anticheat_judge_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_judge_sessions_user", table_name="anticheat_judge_sessions")
    op.drop_table("anticheat_judge_sessions")
