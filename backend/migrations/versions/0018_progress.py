"""S-42: прогресс, достижения, age_group.

- user_profiles.age_group: child|teen|adult|unknown (default unknown).
- py_progress: solved_count/topics/solved_assignments/streaks.
- achievements + user_achievements (PK → бейдж один раз).

Revision ID: 0018_progress
Revises: 0017_reports_requested_by_null
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_progress"
down_revision: str | None = "0017_reports_requested_by_null"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "age_group",
            sa.String(length=12),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.execute(
        "ALTER TABLE user_profiles ADD CONSTRAINT ck_user_profiles_age_group_values "
        "CHECK (age_group IN ('child', 'teen', 'adult', 'unknown'))"
    )

    op.create_table(
        "py_progress",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "solved_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "topics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "solved_assignments",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "current_streak", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "longest_streak", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_solved_on", sa.Date(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_py_progress"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "achievements",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title_ru", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=False, server_default="badge"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("code", name="uq_achievements_code"),
        sa.CheckConstraint(
            "kind IN ('solved', 'streak', 'topics')",
            name="ck_achievements_kind_values",
        ),
    )

    op.create_table(
        "user_achievements",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("achievement_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "awarded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "context",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "achievement_id", name="pk_user_achievements"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["achievement_id"], ["achievements.id"], ondelete="CASCADE"
        ),
    )


def downgrade() -> None:
    op.drop_table("user_achievements")
    op.drop_table("achievements")
    op.drop_table("py_progress")
    op.execute(
        "ALTER TABLE user_profiles DROP CONSTRAINT ck_user_profiles_age_group_values"
    )
    op.drop_column("user_profiles", "age_group")
