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


class AgeGroup(enum.StrEnum):
    CHILD = "child"
    TEEN = "teen"
    ADULT = "adult"
    UNKNOWN = "unknown"


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
    age_group: Mapped[AgeGroup] = mapped_column(
        _str_enum(AgeGroup, 12), nullable=False, default=AgeGroup.UNKNOWN
    )
    # S-83: возрастная группа, подтверждённая учителем класса (trusted-источник
    # для consent enforcement); self-change age_group сбрасывает подтверждение.
    age_group_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    age_group_confirmed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
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

    __table_args__ = (
        # S-83: кто из учителей подтвердил возрастную группу (миграция 0034).
        sa.Index(
            "ix_user_profiles_age_group_confirmed_by", "age_group_confirmed_by"
        ),
    )
