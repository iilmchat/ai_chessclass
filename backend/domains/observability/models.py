"""ORM-модель DLQ фоновых задач (S-73, ADR-016); DDL — миграция 0032."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class FailedJob(Base):
    """Последняя ошибка arq-задачи; job_id уникален (повторные попытки — update)."""

    __tablename__ = "failed_jobs"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    job_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    args: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_type: Mapped[str] = mapped_column(String(128), nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    trace_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="failed"
    )
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('failed', 'retried', 'ignored')", name="status_values"
        ),
    )
