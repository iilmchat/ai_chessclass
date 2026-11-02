"""S-46: voice_usage — фактическое использование озвучки для cost-per-student.

Revision ID: 0022_observability
Revises: 0021_tournaments
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_observability"
down_revision: str | None = "0021_tournaments"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_usage",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("chars", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("cached", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_voice_usage_user", "voice_usage", ["user_id"])
    op.create_index("ix_voice_usage_created", "voice_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_voice_usage_created", table_name="voice_usage")
    op.drop_index("ix_voice_usage_user", table_name="voice_usage")
    op.drop_table("voice_usage")
