"""ORM-модели реестра навыков (Design §10.1, §10.4); DDL — миграция 0003.

`cognitive_skill_events` / `user_skill_scores` (EMA) — этап E-08…E-09.
"""

import enum
from datetime import datetime

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
