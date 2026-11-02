"""ORM-модели прогресса и достижений (S-42)."""

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Date,
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


class PyProgress(Base):
    """Агрегат Python-прогресса: решено, темы, стрики."""

    __tablename__ = "py_progress"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    solved_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    topics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    solved_assignments: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    current_streak: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    longest_streak: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    last_solved_on: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Achievement(Base):
    """Каталог бейджей; code стабилен, threshold — условие."""

    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title_ru: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # solved|streak|topics
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    icon: Mapped[str] = mapped_column(String(16), nullable=False, server_default="badge")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.CheckConstraint(
            "kind IN ('solved', 'streak', 'topics')", name="achievements_kind_values"
        ),
    )


class UserAchievement(Base):
    """Выданный бейдж; PK гарантирует «один раз»."""

    __tablename__ = "user_achievements"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    achievement_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("achievements.id", ondelete="CASCADE"),
        primary_key=True,
    )
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
