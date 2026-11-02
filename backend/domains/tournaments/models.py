"""ORM-модели турниров ботов (S-45): bracket/round-robin без LLM."""

from datetime import datetime

import sqlalchemy as sa
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
    progress: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    total_matches: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    job_id: Mapped[str | None] = mapped_column(String(64))
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    error: Mapped[str | None] = mapped_column(Text)
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
            "status IN ('draft', 'queued', 'running', 'done', 'cancelled', 'failed')",
            name="tournament_status_values",
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


class TournamentMove(Base):
    """Ходы турнирного матча (replay + античит-семплы, S-48)."""

    __tablename__ = "tournament_moves"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tournament_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tournament_matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    bot_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bot_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    fen: Mapped[str] = mapped_column(Text, nullable=False)
    uci: Mapped[str] = mapped_column(String(8), nullable=False)
    agent: Mapped[str] = mapped_column(String(8), nullable=False)  # a | b
    think_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sf_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.Index("ix_tournament_moves_match", "match_id"),
        sa.Index("ix_tournament_moves_tournament", "tournament_id"),
    )
