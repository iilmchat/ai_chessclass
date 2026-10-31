"""ORM-модель античит-флагов (Design §9.4); DDL — миграция 0006."""

import enum
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class FlagKind(enum.StrEnum):
    ENGINE_LIKELINESS = "engine_likeliness"
    LOW_EFFORT = "low_effort"
    TRIVIAL_BOT = "trivial_bot"
    UNEXPLAINED_CODE = "unexplained_code"
    PLAGIARISM_SUSPECTED = "plagiarism_suspected"
    PROFILE_MISMATCH = "profile_mismatch"


class FlagDomain(enum.StrEnum):
    PYTHON = "python"
    CHESS = "chess"
    BOT = "bot"
    CROSS = "cross"


class FlagStatus(enum.StrEnum):
    NEW = "new"
    REVIEWED = "reviewed"
    FALSE_POSITIVE = "false_positive"
    CONFIRMED = "confirmed"


def _str_enum(enum_cls: type[enum.Enum], length: int) -> sa.Enum:
    """Enum-колонка как VARCHAR + CHECK со значениями (не именами) enum."""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
    )


class AnticheatFlag(Base):
    """Флаг для учителя: данные + confidence; решения — только человеком."""

    __tablename__ = "anticheat_flags"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[FlagKind] = mapped_column(_str_enum(FlagKind, 32), nullable=False)
    domain: Mapped[FlagDomain] = mapped_column(_str_enum(FlagDomain, 8), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[FlagStatus] = mapped_column(
        _str_enum(FlagStatus, 16), nullable=False, default=FlagStatus.NEW
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
        CheckConstraint(
            "kind IN ('engine_likeliness', 'low_effort', 'trivial_bot', "
            "'unexplained_code', 'plagiarism_suspected', 'profile_mismatch')",
            name="kind_values",
        ),
        CheckConstraint(
            "domain IN ('python', 'chess', 'bot', 'cross')", name="domain_values"
        ),
        CheckConstraint(
            "status IN ('new', 'reviewed', 'false_positive', 'confirmed')",
            name="status_values",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )
