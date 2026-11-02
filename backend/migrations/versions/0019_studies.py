"""S-43: chess_studies — генерация, ревью и публикация этюдов.

Revision ID: 0019_studies
Revises: 0018_progress
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_studies"
down_revision: str | None = "0018_progress"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chess_studies",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("fen", sa.String(length=128), nullable=False),
        sa.Column("condition_text", sa.Text(), nullable=False),
        sa.Column("theme", sa.String(length=32), nullable=False, server_default="tactics"),
        sa.Column(
            "difficulty", sa.String(length=12), nullable=False, server_default="novice"
        ),
        sa.Column("solution_uci", sa.String(length=8), nullable=False),
        sa.Column(
            "solution_line",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="generated"),
        sa.Column(
            "generator_meta",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('draft', 'review', 'published', 'rejected')",
            name="ck_chess_studies_study_status_values",
        ),
    )
    op.create_index("ix_chess_studies_status", "chess_studies", ["status"])


def downgrade() -> None:
    op.drop_index("ix_chess_studies_status", table_name="chess_studies")
    op.drop_table("chess_studies")
