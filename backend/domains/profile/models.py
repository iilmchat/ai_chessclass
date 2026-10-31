"""ORM-модели профиля (Design §11.2); DDL — миграция 0003_profile_skills."""

import enum
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.levels import Level
from db.base import Base


class BillingTier(enum.StrEnum):
    FREE = "free"
    PRO = "pro"


def _str_enum(enum_cls: type[enum.Enum], length: int) -> sa.Enum:
    """Enum-колонка как VARCHAR + CHECK со значениями (не именами) enum."""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
    )


class UserProfile(Base):
    """1-1 с users; создаётся при регистрации (level=novice, tier=free)."""

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_name: Mapped[str | None] = mapped_column(String(120))
    level: Mapped[Level] = mapped_column(
        _str_enum(Level, 12), nullable=False, default=Level.NOVICE
    )
    billing_tier: Mapped[BillingTier] = mapped_column(
        _str_enum(BillingTier, 12), nullable=False, default=BillingTier.FREE
    )
    prefs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
