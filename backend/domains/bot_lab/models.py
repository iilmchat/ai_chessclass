"""ORM-модели bot_lab (Design §11.2); DDL — миграции 0011/0012."""

import enum
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
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


class MatchResult(enum.StrEnum):
    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"
    TIMEOUT = "timeout"
    ERROR = "error"


class BotStats(Base):
    """Рейтинг бота ученика: Elo + счёт по лестнице (PK user)."""

    __tablename__ = "bot_stats"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    elo: Mapped[Decimal] = mapped_column(
        Numeric(6, 1), nullable=False, server_default="1000"
    )
    wins: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    losses: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    draws: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def _str_enum(enum_cls: type[enum.Enum], length: int) -> sa.Enum:
    """Enum-колонка как VARCHAR + CHECK со значениями (не именами) enum."""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
    )


class BotMatch(Base):
    """Матч версии против оппонента лестницы."""

    __tablename__ = "bot_matches"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bot_versions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    opponent: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[MatchResult] = mapped_column(_str_enum(MatchResult, 8), nullable=False)
    moves_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    elo_delta: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "result IN ('win', 'loss', 'draw', 'timeout', 'error')",
            name="result_values",
        ),
    )


class BotMatchMove(Base):
    """Ходы матча (реплей; семплирование для engine_likeliness — S-19)."""

    __tablename__ = "bot_match_moves"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    match_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bot_matches.id", ondelete="CASCADE"), nullable=False
    )
    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    fen: Mapped[str] = mapped_column(Text, nullable=False)
    uci: Mapped[str] = mapped_column(String(8), nullable=False)
    agent: Mapped[str] = mapped_column(String(16), nullable=False)  # student | opponent
    think_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sf_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
