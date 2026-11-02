"""ORM-модели spaced repetition (S-52): карточки, SM-2 события."""

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


class ReviewCard(Base):
    __tablename__ = "review_cards"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="manual"
    )
    source_ref: Mapped[str | None] = mapped_column(String(120))
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    ease: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, server_default="2.50"
    )
    interval_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    repetitions: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    lapses: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
        sa.UniqueConstraint(
            "user_id", "source_type", "source_ref", name="uq_review_cards_source"
        ),
        sa.Index("ix_review_cards_due", "user_id", "due_at"),
        sa.CheckConstraint(
            "source_type IN ('manual', 'python', 'chess')",
            name="review_source_values",
        ),
    )


class ReviewEvent(Base):
    __tablename__ = "review_events"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    card_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("review_cards.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    quality: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_before: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_after: Mapped[int] = mapped_column(Integer, nullable=False)
    ease_after: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.CheckConstraint(
            "rating IN ('again', 'hard', 'good', 'easy')",
            name="review_rating_values",
        ),
        sa.Index("ix_review_events_user", "user_id", "created_at"),
    )
