"""ORM-модель email outbox (S-83): очередь писем с retry.

Письмо parental consent не отправляется синхронно внутри HTTP-запроса:
строка пишется в outbox, cron `email_outbox_deliver` доставляет её с
экспоненциальным backoff (паттерн TelegramOutbox S-50/S-68). DDL — миграция
0035. В `body` хранится готовое тело письма, включая одноразовую ссылку
согласия: raw-токен в отдельной колонке не дублируется, но остаётся в тексте
письма до успешной доставки (осознанный компромисс ради повторной отправки;
TTL ссылки ограничен parental_consents, retention outbox — план v0.7).
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    DateTime,
    Identity,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class EmailOutbox(Base):
    """Очередь писем: pending/failed повторяются, sent — терминальный."""

    __tablename__ = "email_outbox"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    #: назначение письма: parental_consent и будущие виды (verify/reset)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
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
            name="email_outbox_status_values",
        ),
        sa.Index("ix_email_outbox_status_next", "status", "next_attempt_at"),
    )
