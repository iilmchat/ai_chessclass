"""Бизнес-логика python_teacher: CRUD заданий (admin), сдача, вердикты."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from domains.auth.models import User, UserRole
from domains.python_teacher.grader import grade_solution
from domains.python_teacher.models import (
    AssignmentLevel,
    HintKind,
    PyAssignment,
    PyHint,
    PySubmission,
    Verdict,
)

logger = logging.getLogger(__name__)


async def list_assignments(
    session: AsyncSession,
    level: AssignmentLevel | None,
    page: int,
    page_size: int,
) -> tuple[list[PyAssignment], int]:
    conditions: list = [PyAssignment.is_active.is_(True)]
    if level is not None:
        conditions.append(PyAssignment.level == level)
    total = (
        await session.execute(
            select(func.count()).select_from(PyAssignment).where(*conditions)
        )
    ).scalar_one()
    stmt = (
        select(PyAssignment)
        .where(*conditions)
        .order_by(PyAssignment.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total)


async def get_assignment(session: AsyncSession, assignment_id: int) -> PyAssignment:
    assignment = await session.get(PyAssignment, assignment_id)
    if assignment is None or not assignment.is_active:
        raise AppError("assignment_not_found", "Задание не найдено", 404)
    return assignment


def validate_tests(tests: list[str]) -> None:
    """Assert-тесты: однострочные, начинаются с assert (иначе harness сломается)."""
    for index, test in enumerate(tests):
        if "\n" in test:
            raise AppError(
                "invalid_tests",
                f"Тест №{index} должен быть однострочным (assert-стиль)",
                422,
            )
        if not test.strip().startswith("assert"):
            raise AppError(
                "invalid_tests", f"Тест №{index} должен начинаться с assert", 422
            )


async def create_assignment(
    session: AsyncSession,
    *,
    slug: str,
    title: str,
    level: AssignmentLevel,
    topic: str,
    statement: str,
    starter_code: str,
    tests: list[str],
    hints: list[dict] | None = None,
) -> PyAssignment:
    validate_tests(tests)
    existing = (
        await session.execute(select(PyAssignment).where(PyAssignment.slug == slug))
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError("assignment_exists", f"Задание со слагом {slug!r} уже есть", 409)
    assignment = PyAssignment(
        slug=slug,
        title=title,
        level=level,
        topic=topic,
        statement=statement,
        starter_code=starter_code,
        tests=list(tests),
    )
    session.add(assignment)
    await session.flush()
    for hint in hints or []:
        session.add(
            PyHint(
                assignment_id=assignment.id,
                idx=hint["idx"],
                kind=HintKind(hint["kind"]),
                content=hint["content"],
            )
        )
    await session.flush()
    logger.info("py: создано задание %s (%s)", slug, level.value)
    return assignment


async def update_assignment(
    session: AsyncSession,
    assignment_id: int,
    *,
    title: str | None = None,
    level: AssignmentLevel | None = None,
    statement: str | None = None,
    starter_code: str | None = None,
    tests: list[str] | None = None,
    is_active: bool | None = None,
) -> PyAssignment:
    assignment = await get_assignment(session, assignment_id)
    if tests is not None:
        validate_tests(tests)
        assignment.tests = list(tests)
    if title is not None:
        assignment.title = title
    if level is not None:
        assignment.level = level
    if statement is not None:
        assignment.statement = statement
    if starter_code is not None:
        assignment.starter_code = starter_code
    if is_active is not None:
        assignment.is_active = is_active
    await session.flush()
    return assignment


def _verdict_from_grade(grade) -> Verdict:  # noqa: ANN001 — GradeResult
    return Verdict(grade.verdict)


async def submit(
    session: AsyncSession, user: User, assignment_id: int, code: str
) -> tuple[PySubmission, object]:
    """Сдача: прогон в песочнице → вердикт → сохранение py_submissions (§5.3)."""
    assignment = await get_assignment(session, assignment_id)
    grade = await grade_solution(
        code,
        list(assignment.tests),
        timeout_s=settings.sandbox_timeout_s,
        memory_limit_mb=settings.sandbox_memory_limit_mb,
        max_output_chars=settings.sandbox_max_output_chars,
    )
    submission = PySubmission(
        assignment_id=assignment.id,
        user_id=user.id,
        code=code,
        verdict=_verdict_from_grade(grade),
        passed_tests=grade.passed_tests,
        total_tests=grade.total_tests,
        failed_test=grade.failed_test,
        stdout_digest=grade.stdout_digest,
        duration_ms=grade.duration_ms,
    )
    session.add(submission)
    await session.flush()
    logger.info(
        "py: сдача user_id=%s assignment=%s → %s (%d/%d)",
        user.id, assignment.slug, grade.verdict, grade.passed_tests, grade.total_tests,
    )
    return submission, grade


async def get_submission(
    session: AsyncSession, submission_id: int, user: User
) -> PySubmission:
    submission = await session.get(PySubmission, submission_id)
    if submission is None:
        raise AppError("submission_not_found", "Сдача не найдена", 404)
    if submission.user_id != user.id and user.role not in (UserRole.TEACHER, UserRole.ADMIN):
        raise AppError("auth_forbidden", "Можно смотреть только свои сдачи", 403)
    return submission


def resolve_level_or_none(value: str | None) -> AssignmentLevel | None:
    if value is None:
        return None
    try:
        return AssignmentLevel(value.strip().lower())
    except ValueError:
        raise AppError(
            "invalid_level", "Уровень: novice | intermediate | advanced", 422
        ) from None
