"""ORM-модели python-домена (Design §11.2); DDL — миграция 0005_py_domain."""

import enum
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class AssignmentLevel(enum.StrEnum):
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Verdict(enum.StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RESTRICTED = "restricted"
    ERROR = "error"


class HintKind(enum.StrEnum):
    CONCEPT = "concept"
    STRATEGY = "strategy"
    PSEUDOCODE = "pseudocode"
    CODE = "code"


def _str_enum(enum_cls: type[enum.Enum], length: int) -> sa.Enum:
    """Enum-колонка как VARCHAR + CHECK со значениями (не именами) enum."""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
    )


class PyAssignment(Base):
    """Задание: условие, стартер, тесты (assert-стиль), тема → навык."""

    __tablename__ = "py_assignments"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[AssignmentLevel] = mapped_column(
        _str_enum(AssignmentLevel, 12), nullable=False
    )
    topic: Mapped[str] = mapped_column(String(64), nullable=False)  # slug навыка §10.1
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    starter_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tests: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    checkpoints: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PyHint(Base):
    """Ступень лестницы подсказок (seed; генерируемые — S-09)."""

    __tablename__ = "py_hints"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    assignment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("py_assignments.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 — концептуальная
    kind: Mapped[HintKind] = mapped_column(_str_enum(HintKind, 16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("assignment_id", "idx", name="uq_py_hints_assignment_idx"),
    )


class PySubmission(Base):
    """Попытка ученика + вердикт песочницы (Design §5.3)."""

    __tablename__ = "py_submissions"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    assignment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("py_assignments.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[Verdict] = mapped_column(_str_enum(Verdict, 16), nullable=False)
    passed_tests: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    total_tests: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    failed_test: Mapped[int | None] = mapped_column(Integer)
    stdout_digest: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
