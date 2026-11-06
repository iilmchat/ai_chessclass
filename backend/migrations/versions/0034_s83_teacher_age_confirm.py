"""S-83: подтверждение возрастной группы ученика учителем.

Revision ID: 0034_s83_teacher_age_confirm
Revises: 0033_s74_parental_consent
Create Date: 2026-11-06

Учитель класса — доверенный источник возрастной группы ученика (consent
enforcement v0.6.1): подтверждение хранится в `user_profiles` и сбрасывается,
если ученик сам меняет возраст (self-declared значение снова «не подтверждено»).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_s83_teacher_age_confirm"
down_revision: str | None = "0033_s74_parental_consent"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "age_group_confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "age_group_confirmed_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_user_profiles_age_group_confirmed_by",
        "user_profiles",
        ["age_group_confirmed_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_profiles_age_group_confirmed_by", table_name="user_profiles"
    )
    op.drop_column("user_profiles", "age_group_confirmed_by")
    op.drop_column("user_profiles", "age_group_confirmed_at")
