"""S-67: lms_courses и lms_class_map — маппинг классов на курсы LMS.

Revision ID: 0030_s67_lms_oauth
Revises: 0029_pvp_complaint_review
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_s67_lms_oauth"
down_revision: str | None = "0029_pvp_complaint_review"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lms_courses",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), primary_key=True
        ),
        sa.Column("external_id", sa.String(255), nullable=False, unique=True),
        sa.Column("title_ru", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "lms_class_map",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), primary_key=True
        ),
        sa.Column(
            "class_id",
            sa.BigInteger(),
            sa.ForeignKey("classes.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "course_id",
            sa.BigInteger(),
            sa.ForeignKey("lms_courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activity_ref", sa.String(512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_lms_class_map_course", "lms_class_map", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_lms_class_map_course", table_name="lms_class_map")
    op.drop_table("lms_class_map")
    op.drop_table("lms_courses")
