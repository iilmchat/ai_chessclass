"""ORM-модель кэша озвучки (S-44): один платный синтез на текст."""

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, Identity, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class VoiceAudio(Base):
    """Метаданные аудиофайла; text_hash уникален для voice+model+text."""

    __tablename__ = "voice_audio"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    voice_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    chars: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, server_default="0"
    )
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="elevenlabs"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
