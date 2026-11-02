"""ORM-модели этюдов (S-43): генерация → ревью → публикация."""

import enum
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class StudyStatus(enum.StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    REJECTED = "rejected"


def _str_enum(enum_cls: type[enum.Enum], length: int) -> sa.Enum:
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
    )


class ChessStudy(Base):
    """Этюд: FEN + условие + эталонный ход/линия + модерация."""

    __tablename__ = "chess_studies"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    fen: Mapped[str] = mapped_column(String(128), nullable=False)
    condition_text: Mapped[str] = mapped_column(Text, nullable=False)
    theme: Mapped[str] = mapped_column(String(32), nullable=False, server_default="tactics")
    difficulty: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="novice"
    )
    solution_uci: Mapped[str] = mapped_column(String(8), nullable=False)
    solution_line: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[StudyStatus] = mapped_column(
        _str_enum(StudyStatus, 12), nullable=False, default=StudyStatus.DRAFT
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="generated"
    )
    generator_meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
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
        sa.CheckConstraint(
            "status IN ('draft', 'review', 'published', 'rejected')",
            name="study_status_values",
        ),
        sa.Index("ix_chess_studies_status", "status"),
    )
