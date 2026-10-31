"""S-09: эталоны решений, LLM-комментарии, античит-флаги, события навыков.

Design §5.4 (hint ladder), §5.3 (py_feedback), §9.4 (anticheat_flags:
id/user/kind/domain/source_ref/confidence/evidence/status/review/note),
§10.2 (cognitive_skill_events). Решает человек, не модель (ADR-005).

Revision ID: 0006_py_hints_cognitive
Revises: 0005_py_domain
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_py_hints_cognitive"
down_revision: str | None = "0005_py_domain"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

FLAG_KINDS = (
    "engine_likeliness",
    "low_effort",
    "trivial_bot",
    "unexplained_code",
    "plagiarism_suspected",
    "profile_mismatch",
)


def upgrade() -> None:
    op.create_table(
        "py_reference_solutions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("assignment_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["assignment_id"], ["py_assignments.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_py_reference_assignment", "py_reference_solutions", ["assignment_id"], unique=True
    )

    op.create_table(
        "py_feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("submission_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("route", sa.String(length=64), nullable=False),
        sa.Column("model_used", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["py_submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_py_feedback_submission", "py_feedback", ["submission_id"], unique=True
    )

    op.create_table(
        "anticheat_flags",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("domain", sa.String(length=8), nullable=False),
        sa.Column("source_ref", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column(
            "evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            f"kind IN ({', '.join(repr(k) for k in FLAG_KINDS)})", name="kind_values"
        ),
        sa.CheckConstraint(
            "domain IN ('python', 'chess', 'bot', 'cross')", name="domain_values"
        ),
        sa.CheckConstraint(
            "status IN ('new', 'reviewed', 'false_positive', 'confirmed')",
            name="status_values",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_anticheat_flags_user", "anticheat_flags", ["user_id"])
    op.create_index("ix_anticheat_flags_kind_status", "anticheat_flags", ["kind", "status"])

    op.create_table(
        "cognitive_skill_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("domain", sa.String(length=8), nullable=False),
        sa.Column("weight", sa.Numeric(6, 3), nullable=False),
        sa.Column(
            "meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("domain IN ('python', 'chess')", name="domain_values"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_cognitive_events_user_skill", "cognitive_skill_events", ["user_id", "skill_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_cognitive_events_user_skill", table_name="cognitive_skill_events")
    op.drop_table("cognitive_skill_events")
    op.drop_index("ix_anticheat_flags_kind_status", table_name="anticheat_flags")
    op.drop_index("ix_anticheat_flags_user", table_name="anticheat_flags")
    op.drop_table("anticheat_flags")
    op.drop_index("uq_py_feedback_submission", table_name="py_feedback")
    op.drop_table("py_feedback")
    op.drop_index("uq_py_reference_assignment", table_name="py_reference_solutions")
    op.drop_table("py_reference_solutions")
