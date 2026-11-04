"""ORM-модели LMS LRS (S-49): идемпотентная доставка xAPI statements."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class LmsCourse(Base):
    """LMS-курс (S-67): внешний курс в LMS, к которому привязываются классы."""

    __tablename__ = "lms_courses"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LmsClassMap(Base):
    """Привязка класса к курсу (S-67): база activity id для xAPI.

    activity_ref — префикс activity id (например, https://lms…/courses/42);
    skill-объект строится f"{activity_ref.rstrip('/')}/skills/{slug}".
    Один класс — не более одного маппинга.
    """

    __tablename__ = "lms_class_map"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    class_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("classes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    course_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lms_courses.id", ondelete="CASCADE"), nullable=False
    )
    activity_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (sa.Index("ix_lms_class_map_course", "course_id"),)


class LrsDelivery(Base):
    __tablename__ = "lrs_deliveries"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    statement_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    response_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name="lrs_delivery_status_values",
        ),
        sa.Index("ix_lrs_deliveries_status", "status"),
    )
