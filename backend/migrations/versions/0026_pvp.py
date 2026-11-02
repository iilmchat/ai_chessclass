"""S-51: pvp_rooms / pvp_ratings / pvp_complaints.

Revision ID: 0026_pvp
Revises: 0025_telegram
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_pvp"
down_revision: str | None = "0025_telegram"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pvp_rooms",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("host_user_id", sa.BigInteger(), nullable=False),
        sa.Column("host_bot_id", sa.BigInteger(), nullable=False),
        sa.Column("guest_user_id", sa.BigInteger(), nullable=True),
        sa.Column("guest_bot_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="waiting"),
        sa.Column("rated", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("tournament_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["host_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["host_bot_id"], ["bot_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["guest_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["guest_bot_id"], ["bot_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"], ["tournaments.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("code", name="uq_pvp_rooms_code"),
        sa.CheckConstraint(
            "status IN ('waiting', 'ready', 'running', 'done', 'cancelled', 'failed')",
            name="ck_pvp_rooms_pvp_room_status_values",
        ),
    )
    op.create_index("ix_pvp_rooms_status", "pvp_rooms", ["status"])
    op.create_index("ix_pvp_rooms_code", "pvp_rooms", ["code"])
    op.create_table(
        "pvp_ratings",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("elo", sa.Numeric(6, 1), nullable=False, server_default="1000"),
        sa.Column("wins", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("losses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("draws", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name="pk_pvp_ratings"),
    )
    op.create_table(
        "pvp_complaints",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("room_id", sa.BigInteger(), nullable=False),
        sa.Column("reporter_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["room_id"], ["pvp_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('open', 'reviewed', 'rejected')",
            name="ck_pvp_complaints_pvp_complaint_status_values",
        ),
    )
    op.create_index("ix_pvp_complaints_status", "pvp_complaints", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pvp_complaints_status", table_name="pvp_complaints")
    op.drop_table("pvp_complaints")
    op.drop_table("pvp_ratings")
    op.drop_index("ix_pvp_rooms_code", table_name="pvp_rooms")
    op.drop_index("ix_pvp_rooms_status", table_name="pvp_rooms")
    op.drop_table("pvp_rooms")
