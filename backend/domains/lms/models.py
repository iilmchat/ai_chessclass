"""ORM-модели LMS LRS (S-49): идемпотентная доставка xAPI statements."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, Identity, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class LrsDelivery(Base):
    __tablename__ = "lrs_deliveries"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    statement_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    response_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name="lrs_delivery_status_values",
        ),
        sa.Index("ix_lrs_deliveries_status", "status"),
    )
