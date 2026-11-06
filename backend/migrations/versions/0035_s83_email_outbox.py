"""S-83: email_outbox — очередь писем parental consent с retry/backoff.

Revision ID: 0035_s83_email_outbox
Revises: 0034_s83_teacher_age_confirm
Create Date: 2026-11-06

Письмо parental consent ставится в очередь (pending) и доставляется cron
`app.worker.email_outbox_deliver`; ошибки SMTP повторяются с backoff
(2^n секунд, максимум 3600), после EMAIL_OUTBOX_MAX_ATTEMPTS строка
паркуется. Гранты роли chess_app на новую таблицу выдаются
ALTER DEFAULT PRIVILEGES из S-72 (миграция 0031).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_s83_email_outbox"
down_revision: str | None = "0034_s83_teacher_age_confirm"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_outbox",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), primary_key=True
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=12), nullable=False, server_default="pending"
        ),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name="email_outbox_status_values",
        ),
    )
    op.create_index(
        "ix_email_outbox_status_next",
        "email_outbox",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_outbox_status_next", table_name="email_outbox")
    op.drop_table("email_outbox")
