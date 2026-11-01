"""ORM-модели классов (S-40): класс учителя и его ученики.

DDL — миграция 0015_classes. Инвайт-код — короткий код класса; ротация
доступна владельцу. Роль участника всегда student (учитель — owner).
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Classroom(Base):
    """Класс/группа, принадлежащая учителю."""

    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    teacher_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    invite_code: Mapped[str] = mapped_column(
        String(16), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (sa.Index("ix_classes_teacher", "teacher_id"),)


class ClassMember(Base):
    """Ученик в классе; уникальность пары class_id + user_id."""

    __tablename__ = "class_members"

    class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (sa.Index("ix_class_members_user", "user_id"),)
