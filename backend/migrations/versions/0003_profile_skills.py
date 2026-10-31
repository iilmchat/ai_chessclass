"""S-03: профиль + когнитивный реестр — user_profiles, skills, skill_links.

Design §11.2 (shared-таблицы). user_profiles — 1:1 с users (PK = FK);
skills/skill_links — seed-реестр (§10.1, §10.4). created_at/updated_at
сверх каталога (аудит) — зафиксировано в docs/SPEC.md.

Revision ID: 0003_profile_skills
Revises: 0002_auth_domain
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_profile_skills"
down_revision: str | None = "0002_auth_domain"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("level", sa.String(length=12), nullable=False, server_default="novice"),
        sa.Column(
            "billing_tier", sa.String(length=12), nullable=False, server_default="free"
        ),
        sa.Column(
            "prefs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
        sa.CheckConstraint("level IN ('novice', 'intermediate', 'advanced')", name="level_values"),
        sa.CheckConstraint("billing_tier IN ('free', 'pro')", name="billing_tier_values"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    # backfill: профиль каждому существующему юзеру (легаси до S-03)
    op.execute(
        "INSERT INTO user_profiles (user_id, level, billing_tier, prefs) "
        "SELECT id, 'novice', 'free', '{}'::jsonb FROM users u "
        "WHERE NOT EXISTS (SELECT 1 FROM user_profiles up WHERE up.user_id = u.id)"
    )

    op.create_table(
        "skills",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title_ru", sa.String(length=120), nullable=False),
        sa.Column("domain", sa.String(length=8), nullable=False),
        sa.Column(
            "domain_ref",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("domain IN ('python', 'chess')", name="domain_values"),
    )
    op.create_index("uq_skills_slug", "skills", ["slug"], unique=True)

    op.create_table(
        "skill_links",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("from_skill_id", sa.BigInteger(), nullable=False),
        sa.Column("to_skill_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "weight", sa.Numeric(4, 3), nullable=False, server_default=sa.text("1.000")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["from_skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("from_skill_id", "to_skill_id", name="uq_skill_links_pair"),
    )


def downgrade() -> None:
    op.drop_table("skill_links")
    op.drop_index("uq_skills_slug", table_name="skills")
    op.drop_table("skills")
    op.drop_table("user_profiles")
