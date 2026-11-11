"""ORM-модель legal hold (S-98): удержание данных субъекта."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class LegalHold(Base):
    """Активный/отозванный legal hold по субъекту (обычно user)."""

    __tablename__ = "legal_holds"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    subject_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="user"
    )
    #: ID субъекта строкой: user id, email или иной идентификатор.
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        sa.Index("ix_legal_holds_subject", "subject_type", "subject_id"),
        sa.Index("ix_legal_holds_expires", "expires_at"),
    )
