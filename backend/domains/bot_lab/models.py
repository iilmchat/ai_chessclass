"""ORM-модели bot_lab (Design §11.2); DDL — миграция 0011_bot_versions."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class BotVersion(Base):
    """Версия кода бота ученика (is_active — рабочая версия)."""

    __tablename__ = "bot_versions"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    entry: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="choose_move"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
