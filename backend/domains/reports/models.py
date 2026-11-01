"""ORM-модель отчётов (S-25); DDL — миграция 0014_reports."""

import enum
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ReportKind(enum.StrEnum):
    PARENT = "parent"
    TEACHER = "teacher"


class ReportPdf(Base):
    """Сгенерированный PDF-отчёт (файл на volume, запись — метаданные)."""

    __tablename__ = "reports_pdfs"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    kind: Mapped[ReportKind] = mapped_column(
        String(16), nullable=False, server_default="parent"
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.CheckConstraint("kind IN ('parent', 'teacher')", name="kind_values"),
    )
