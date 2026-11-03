"""ORM-модели PvP-комнат (S-51): приглашения, отдельный рейтинг, жалобы."""

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
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


class PvpRoom(Base):
    __tablename__ = "pvp_rooms"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    host_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    host_bot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bot_versions.id", ondelete="CASCADE"), nullable=False
    )
    guest_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    guest_bot_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bot_versions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="waiting"
    )
    rated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tournament_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tournaments.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('waiting', 'ready', 'running', 'done', 'cancelled', 'failed')",
            name="pvp_room_status_values",
        ),
        sa.Index("ix_pvp_rooms_status", "status"),
        sa.Index("ix_pvp_rooms_code", "code"),
    )


class PvpRating(Base):
    __tablename__ = "pvp_ratings"

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


class PvpComplaint(Base):
    __tablename__ = "pvp_complaints"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    room_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pvp_rooms.id", ondelete="CASCADE"), nullable=False
    )
    reporter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="open"
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('open', 'reviewed', 'rejected')",
            name="pvp_complaint_status_values",
        ),
        sa.Index("ix_pvp_complaints_status", "status"),
    )
