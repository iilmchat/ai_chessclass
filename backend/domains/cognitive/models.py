"""ORM-модели когнитивного ядра (Design §10.1, §10.2, §10.4).

Реестр/связи — миграция 0003; события — 0006. EMA-скоры (user_skill_scores)
— E-08.
"""

import enum
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SkillDomain(enum.StrEnum):
    PYTHON = "python"
    CHESS = "chess"


def _str_enum(enum_cls: type[enum.Enum], length: int) -> sa.Enum:
    """Enum-колонка как VARCHAR + CHECK со значениями (не именами) enum."""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
    )


class Skill(Base):
    """Навык реестра (11 шт., seed); slug стабилен для событий/весов."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title_ru: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[SkillDomain] = mapped_column(_str_enum(SkillDomain, 8), nullable=False)
    domain_ref: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SkillLink(Base):
    """Кросс-доменная связь навыков (seed, §10.4): python-навык → chess-навык."""

    __tablename__ = "skill_links"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    from_skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    to_skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    weight: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default="1.000"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("from_skill_id", "to_skill_id", name="uq_skill_links_pair"),
    )


class SkillEvent(Base):
    """Событие навыка (§10.2): сдача, подсказка (минус), матч, judge-сессия."""

    __tablename__ = "cognitive_skill_events"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[SkillDomain] = mapped_column(_str_enum(SkillDomain, 8), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserSkillScore(Base):
    """Недельный EMA-скор навыка (§10.3): score 0..100, PK user+skill."""

    __tablename__ = "user_skill_scores"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    week: Mapped[str] = mapped_column(String(8), nullable=False)  # 2026-W44
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
