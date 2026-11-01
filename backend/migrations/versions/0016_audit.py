"""S-41: роль auditor + журнал аудита.

- users.role: добавляем 'auditor' (read-only).
- audit_logs: кто/что/когда/источник + target/meta/request_id.

Revision ID: 0016_audit
Revises: 0015_classes
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_audit"
down_revision: str | None = "0015_classes"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Имя CHECK уже с префиксом ck_users_; op.drop_constraint применил бы
    # naming convention повторно — используем явный SQL.
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role_values")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_role_values "
        "CHECK (role IN ('student', 'teacher', 'admin', 'auditor'))"
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("actor_role", sa.String(length=16), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="api"),
        sa.Column(
            "meta",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_actor", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_created", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role_values")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_role_values "
        "CHECK (role IN ('student', 'teacher', 'admin'))"
    )
