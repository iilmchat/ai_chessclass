"""ORM-модель родительского согласия (S-74, ADR-019); DDL — миграция 0033."""

import enum
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ConsentStatus(enum.StrEnum):
    PENDING = "pending"
    GRANTED = "granted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ParentalConsent(Base):
    """Одноразовый consent-flow: токен хранится только SHA-256-хэшем."""

    __tablename__ = "parental_consents"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    parent_email: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[ConsentStatus] = mapped_column(
        sa.Enum(
            ConsentStatus,
            native_enum=False,
            length=16,
            values_callable=lambda e: [member.value for member in e],
        ),
        nullable=False,
        default=ConsentStatus.PENDING,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'granted', 'revoked', 'expired')",
            name="status_values",
        ),
        sa.Index("ix_parental_consents_user_status", "user_id", "status"),
        sa.Index("ix_parental_consents_expires", "expires_at"),
    )
