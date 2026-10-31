"""S-08: python-домен — py_assignments, py_hints, py_submissions (Design §11.2).

Тесты — assert-стиль в JSONB (list[str]); slug задания — ключ идемпотентных
сидов (сверх каталога, SPEC §3.3). created_at/updated_at — аудит.

Revision ID: 0005_py_domain
Revises: 0004_llm_economy
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_py_domain"
down_revision: str | None = "0004_llm_economy"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "py_assignments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("level", sa.String(length=12), nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("starter_code", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "tests",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "checkpoints",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
            "level IN ('novice', 'intermediate', 'advanced')", name="level_values"
        ),
    )
    op.create_index("uq_py_assignments_slug", "py_assignments", ["slug"], unique=True)
    op.create_index("ix_py_assignments_level", "py_assignments", ["level"])
    op.create_index("ix_py_assignments_topic", "py_assignments", ["topic"])

    op.create_table(
        "py_hints",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("assignment_id", sa.BigInteger(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "kind IN ('concept', 'strategy', 'pseudocode', 'code')",
            name="kind_values",
        ),
        sa.ForeignKeyConstraint(["assignment_id"], ["py_assignments.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_py_hints_assignment_idx", "py_hints", ["assignment_id", "idx"], unique=True
    )

    op.create_table(
        "py_submissions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("assignment_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("passed_tests", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tests", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_test", sa.Integer(), nullable=True),
        sa.Column("stdout_digest", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "verdict IN ('passed', 'failed', 'timeout', 'restricted', 'error')",
            name="verdict_values",
        ),
        sa.ForeignKeyConstraint(["assignment_id"], ["py_assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_py_submissions_user_created", "py_submissions", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_py_submissions_assignment", "py_submissions", ["assignment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_py_submissions_assignment", table_name="py_submissions")
    op.drop_index("ix_py_submissions_user_created", table_name="py_submissions")
    op.drop_table("py_submissions")
    op.drop_index("uq_py_hints_assignment_idx", table_name="py_hints")
    op.drop_table("py_hints")
    op.drop_index("ix_py_assignments_topic", table_name="py_assignments")
    op.drop_index("ix_py_assignments_level", table_name="py_assignments")
    op.drop_index("uq_py_assignments_slug", table_name="py_assignments")
    op.drop_table("py_assignments")
