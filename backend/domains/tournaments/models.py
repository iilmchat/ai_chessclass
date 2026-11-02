"""ORM-модели турниров ботов (S-45): bracket/round-robin без LLM."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    format: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="bracket"
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="draft"
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        sa.CheckConstraint(
            "format IN ('bracket', 'round_robin')", name="tournament_format_values"
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'running', 'done')", name="tournament_status_values"
        ),
    )


class TournamentParticipant(Base):
    __tablename__ = "tournament_participants"

    tournament_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bot_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bot_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    losses: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    draws: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    points: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    rank: Mapped[int | None] = mapped_column(Integer)


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tournament_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
    )
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    match_no: Mapped[int] = mapped_column(Integer, nullable=False)
    bot_a_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bot_versions.id", ondelete="CASCADE"), nullable=False
    )
    bot_b_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bot_versions.id", ondelete="CASCADE"), nullable=False
    )
    winner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bot_versions.id", ondelete="SET NULL")
    )
    result: Mapped[str] = mapped_column(String(8), nullable=False)  # a|b|draw
    moves_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
