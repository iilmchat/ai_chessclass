"""S-40: classes + class_members (классы учителя и участники).

Revision ID: 0015_classes
Revises: 0014_reports
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_classes"
down_revision: str | None = "0014_reports"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("teacher_id", sa.BigInteger(), nullable=False),
        sa.Column("invite_code", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("invite_code", name="uq_classes_invite_code"),
    )
    op.create_index("ix_classes_teacher", "classes", ["teacher_id"])

    op.create_table(
        "class_members",
        sa.Column("class_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("class_id", "user_id", name="pk_class_members"),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_class_members_user", "class_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_class_members_user", table_name="class_members")
    op.drop_table("class_members")
    op.drop_index("ix_classes_teacher", table_name="classes")
    op.drop_table("classes")
