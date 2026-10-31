"""S-05: экономика LLM — llm_calls (журнал вызовов) + usage_daily (агрегат).

Design §8.5: user_id, route, model_requested/model_used, level, tokens,
cost_in/cost_out Numeric(12,4), latency_ms, status, task_kind, fallback_from.
Агрегат usage_daily(user_id, day) → токены/₽; квота дня — Redis.

Revision ID: 0004_llm_economy
Revises: 0003_profile_skills
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_llm_economy"
down_revision: str | None = "0003_profile_skills"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("route", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=12), nullable=False),
        sa.Column("model_requested", sa.String(length=64), nullable=False),
        sa.Column("model_used", sa.String(length=64), nullable=False),
        sa.Column("fallback_from", sa.String(length=64), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_in", sa.Numeric(12, 4), nullable=True),
        sa.Column("cost_out", sa.Numeric(12, 4), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("task_kind", sa.String(length=8), nullable=False, server_default="sync"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'echo', 'error')", name="status_values"
        ),
        sa.CheckConstraint(
            "task_kind IN ('sync', 'async')", name="task_kind_values"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_llm_calls_user_created", "llm_calls", ["user_id", "created_at"])
    op.create_index("ix_llm_calls_route", "llm_calls", ["route"])

    op.create_table(
        "usage_daily",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("tokens_in", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("tokens_out", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "cost_total", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("user_id", "day", name="pk_usage_daily"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("usage_daily")
    op.drop_index("ix_llm_calls_route", table_name="llm_calls")
    op.drop_index("ix_llm_calls_user_created", table_name="llm_calls")
    op.drop_table("llm_calls")
