"""ORM-модель фактического использования озвучки (S-46).

`voice_audio` — глобальный кэш; `voice_usage` — кто и сколько запросил,
включая cache-hit (cost=0, cached=true). Нужна для cost-per-student.
"""

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class VoiceUsage(Base):
    __tablename__ = "voice_usage"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    chars: Mapped[int] = mapped_column(Integer, nullable=False)
    cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, server_default="0"
    )
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.Index("ix_voice_usage_user", "user_id"),
        sa.Index("ix_voice_usage_created", "created_at"),
    )
