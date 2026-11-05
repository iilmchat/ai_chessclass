"""S-73: DLQ arq-задач + trace_id в llm_calls.

Revision ID: 0032_s73_async_tracing
Revises: 0031_s72_rls_isolation
Create Date: 2026-11-05

ADR-016: failed_jobs хранит последнюю ошибку задачи по job_id (upsert из
`core.jobs.track_job`). ADR-017: llm_calls.trace_id связывает FinOps-строку
с HTTP-запросом/arq-задачей.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_s73_async_tracing"
down_revision: str | None = "0031_s72_rls_isolation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_calls", sa.Column("trace_id", sa.String(length=32), nullable=True)
    )
    op.create_index("ix_llm_calls_trace", "llm_calls", ["trace_id"])

    op.create_table(
        "failed_jobs",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(always=True), primary_key=True
        ),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("task", sa.String(length=64), nullable=False),
        sa.Column(
            "args",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_type", sa.String(length=128), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="failed"),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('failed', 'retried', 'ignored')", name="status_values"
        ),
        sa.UniqueConstraint("job_id", name="uq_failed_jobs_job_id"),
    )
    op.create_index("ix_failed_jobs_failed_at", "failed_jobs", ["failed_at"])
    op.create_index("ix_failed_jobs_task_status", "failed_jobs", ["task", "status"])


def downgrade() -> None:
    op.drop_index("ix_failed_jobs_task_status", table_name="failed_jobs")
    op.drop_index("ix_failed_jobs_failed_at", table_name="failed_jobs")
    op.drop_table("failed_jobs")
    op.drop_index("ix_llm_calls_trace", table_name="llm_calls")
    op.drop_column("llm_calls", "trace_id")
