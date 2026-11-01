"""S-16: user_skill_scores — недельные EMA по навыкам (Design §10.3).

PK (user_id, skill_id); week — ISO-неделя (YYYY-Www строкой для читаемости);
score 0..100. Пересчёт — arq `scores:recalc` (nightly).

Revision ID: 0010_skill_scores
Revises: 0009_rag
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_skill_scores"
down_revision: str | None = "0009_rag"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_skill_scores",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("week", sa.String(length=8), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("user_id", "skill_id", name="pk_user_skill_scores"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("user_skill_scores")
