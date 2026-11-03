"""S-65: pvp_complaints — reviewed_by/reviewed_at/note (workflow жалоб).

Revision ID: 0029_pvp_complaint_review
Revises: 0028_rag_editor
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_pvp_complaint_review"
down_revision: str | None = "0028_rag_editor"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pvp_complaints",
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "pvp_complaints",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pvp_complaints",
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_pvp_complaints_reviewed_by",
        "pvp_complaints",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_pvp_complaints_reviewed_by", "pvp_complaints", type_="foreignkey"
    )
    op.drop_column("pvp_complaints", "note")
    op.drop_column("pvp_complaints", "reviewed_at")
    op.drop_column("pvp_complaints", "reviewed_by")
