"""ORM-модели chess_lab (Design §11.2); DDL — миграции 0007/0008."""

import enum
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ChessPosition(Base):
    """Позиция ученика + последние факты/объяснение (upsert по user+fen)."""

    __tablename__ = "chess_positions"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fen: Mapped[str] = mapped_column(String(128), nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GameSource(enum.StrEnum):
    UPLOAD = "upload"
    SAMPLE = "sample"


class AnalysisStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


def _str_enum(enum_cls: type[enum.Enum], length: int) -> sa.Enum:
    """Enum-колонка как VARCHAR + CHECK со значениями (не именами) enum."""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
    )


class ChessGame(Base):
    """Загруженная партия (PGN, ≤ 2 МБ)."""

    __tablename__ = "chess_games"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    pgn: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[GameSource] = mapped_column(
        _str_enum(GameSource, 16), nullable=False, default=GameSource.UPLOAD
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChessAnalysis(Base):
    """Разбор партии: SF-факты (ходы/блюндеры) + LLM-объяснения по ply."""

    __tablename__ = "chess_analyses"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    game_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chess_games.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        _str_enum(AnalysisStatus, 16), nullable=False, default=AnalysisStatus.PENDING
    )
    sf: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    llm: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
