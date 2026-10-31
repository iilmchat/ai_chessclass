"""ORM-модели LLM-экономики (Design §8.5); DDL — миграция 0004_llm_economy."""

from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class LLMCall(Base):
    """Журнал каждого вызова шлюза (FinOps-основа)."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    route: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(12), nullable=False)
    model_requested: Mapped[str] = mapped_column(String(64), nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    fallback_from: Mapped[str | None] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    tokens_out: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    cost_in: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    cost_out: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    task_kind: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="sync"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('ok', 'echo', 'error')", name="status_values"),
        CheckConstraint("task_kind IN ('sync', 'async')", name="task_kind_values"),
    )


class UsageDaily(Base):
    """Агрегат расхода по пользователю и дню (PK — пара)."""

    __tablename__ = "usage_daily"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    tokens_in: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=sa.text("0")
    )
    tokens_out: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=sa.text("0")
    )
    cost_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, server_default=sa.text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
