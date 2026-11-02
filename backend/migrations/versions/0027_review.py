"""S-52: review_cards / review_events (SM-2).

Revision ID: 0027_review
Revises: 0026_pvp
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_review"
down_revision: str | None = "0026_pvp"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_cards",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String(length=120), nullable=True),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("ease", sa.Numeric(4, 2), nullable=False, server_default="2.50"),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lapses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "due_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("suspended", sa.Boolean(), nullable=False, server_default=sa.false()),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "source_type", "source_ref", name="uq_review_cards_source"
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'python', 'chess')",
            name="ck_review_cards_review_source_values",
        ),
    )
    op.create_index("ix_review_cards_due", "review_cards", ["user_id", "due_at"])
    op.create_table(
        "review_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.String(length=8), nullable=False),
        sa.Column("quality", sa.Integer(), nullable=False),
        sa.Column("interval_before", sa.Integer(), nullable=False),
        sa.Column("interval_after", sa.Integer(), nullable=False),
        sa.Column("ease_after", sa.Numeric(4, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["review_cards.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "rating IN ('again', 'hard', 'good', 'easy')",
            name="ck_review_events_review_rating_values",
        ),
    )
    op.create_index("ix_review_events_user", "review_events", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_review_events_user", table_name="review_events")
    op.drop_table("review_events")
    op.drop_index("ix_review_cards_due", table_name="review_cards")
    op.drop_table("review_cards")
