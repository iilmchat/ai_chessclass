"""Бизнес-логика python_teacher: CRUD заданий (admin), сдача, вердикты,
лестница подсказок (§5.4), LLM-комментарий, low_effort, события навыков."""

import logging
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from core.authz import ensure_can_access_submission
from core.config import settings
from core.errors import AppError
from core.levels import Level
from domains.anticheat.service import check_low_effort
from domains.auth.models import User, UserRole
from domains.cognitive.events import (
    WEIGHT_HINT_LLM,
    WEIGHT_HINT_SEEDED,
    WEIGHT_SOLUTION_OPEN,
    emit_skill_event,
)
from domains.cognitive.models import SkillDomain
from domains.profile.models import UserProfile
from domains.progress.service import record_passed_solution
from domains.python_teacher.grader import grade_solution
from domains.python_teacher.models import (
    AssignmentLevel,
    HintKind,
    PyAssignment,
    PyFeedback,
    PyHint,
    PyReferenceSolution,
    PySubmission,
    Verdict,
)
from llm.gateway import LLMCallContext, llm_generate
from llm.prompts.builder import build_messages

logger = logging.getLogger(__name__)

#: решение открывается после N неудачных попыток (или учителем/admin — §5.4)
SOLUTION_LOCK_ATTEMPTS = 3

# веса сдачи (§5.3: emit при любой сдаче; вес меньше при неудаче)
WEIGHT_SUBMIT_PASSED = Decimal("1.000")
WEIGHT_SUBMIT_FAILED = Decimal("0.300")


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


async def get_submission(
    session: AsyncSession, submission_id: int, user: User
) -> PySubmission:
    # S-91: teacher — только сдачи учеников своих классов, не любые.
    return await ensure_can_access_submission(user, submission_id, session)


async def _user_level(session: AsyncSession, user: User) -> Level:
    """Уровень ученика из профиля (fallback novice)."""
    profile = await session.get(UserProfile, user.id)
    return profile.level if profile is not None else Level.NOVICE


async def _user_tier(session: AsyncSession, user: User) -> str:
    profile = await session.get(UserProfile, user.id)
    return profile.billing_tier.value if profile is not None else "free"


async def _failed_attempts(session: AsyncSession, user_id: int, assignment_id: int) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(PySubmission)
                .where(
                    PySubmission.user_id == user_id,
                    PySubmission.assignment_id == assignment_id,
                    PySubmission.verdict != Verdict.PASSED,
                )
            )
        ).scalar_one()
    )


# --- лестница подсказок (Design §5.4)


async def _rag_knowledge(session: AsyncSession, topic: str, level: Level) -> list[str]:
    """RAG-контекст (§8.6): топ-2 чанка базы знаний по теме задания."""
    from rag import retrieval

    try:
        hits = await retrieval.search(
            session, topic, k=2, domains=["python", "general"]
        )
    except Exception as exc:  # noqa: BLE001 — RAG не ломает ассистента
        logger.warning("py: RAG-контекст недоступен: %s", exc)
        return []
    return [f"{hit['titleRu']}: {hit['text'][:300]}" for hit in hits]


async def get_hint(
    session: AsyncSession, redis, user: User, assignment_id: int, hint_idx: int
) -> dict:
    """Ступень лестницы: seeded → по исчерпании LLM-подсказка. События — минус."""
    assignment = await get_assignment(session, assignment_id)
    seeded = (
        await session.execute(
            select(PyHint)
            .where(PyHint.assignment_id == assignment.id)
            .order_by(PyHint.idx)
        )
    ).scalars().all()

    level = await _user_level(session, user)
    meta = {"assignmentId": assignment.id, "hintIdx": hint_idx}

    if 0 <= hint_idx < len(seeded):
        hint = seeded[hint_idx]
        source = "seeded"
        content = hint.content
        kind = hint.kind.value
        weight = WEIGHT_HINT_SEEDED
    else:
        llm_idx = hint_idx - len(seeded) + 1
        knowledge = await _rag_knowledge(session, assignment.topic, level)
        messages = build_messages(
            "python_teacher.hint",
            level,
            request=(
                f"Дай очередную подсказку (ступень {llm_idx}) к заданию. "
                "Готовое решение не раскрывай."
            ),
            facts=[
                f"Задание: {assignment.title}",
                f"Тема: {assignment.topic}",
                f"Условие: {assignment.statement[:400]}",
                f"Сеед-подсказок уже открыто: {len(seeded)}",
            ],
            knowledge=knowledge,
        )
        result = await llm_generate(
            session,
            redis,
            route="python_teacher.hint",
            level=level,
            messages=messages,
            ctx=LLMCallContext(
                user_id=user.id, billing_tier=await _user_tier(session, user)
            ),
        )
        source = "llm"
        content = result.text
        kind = HintKind.PSEUDOCODE.value if level is Level.ADVANCED else HintKind.STRATEGY.value
        weight = WEIGHT_HINT_LLM

    if user.role is UserRole.STUDENT:
        await emit_skill_event(
            session,
            user_id=user.id,
            skill_slug=assignment.topic,
            domain=SkillDomain.PYTHON,
            weight=weight,
            meta=meta,
        )
        await session.flush()
    return {"idx": hint_idx, "kind": kind, "content": content, "source": source}


# --- решение (после N неудач либо учителю; §5.4)


async def get_solution(
    session: AsyncSession, user: User, assignment_id: int
) -> dict:
    assignment = await get_assignment(session, assignment_id)
    if user.role is UserRole.STUDENT:
        failed = await _failed_attempts(session, user.id, assignment.id)
        if failed < SOLUTION_LOCK_ATTEMPTS:
            raise AppError(
                "solution_locked",
                f"Решение откроется после {SOLUTION_LOCK_ATTEMPTS} неудачных "
                f"попыток (у вас: {failed})",
                403,
            )
    ref = (
        await session.execute(
            select(PyReferenceSolution).where(
                PyReferenceSolution.assignment_id == assignment.id
            )
        )
    ).scalar_one_or_none()
    if ref is None:
        raise AppError("solution_not_found", "Эталон решения не заведён", 404)
    if user.role is UserRole.STUDENT:
        await emit_skill_event(
            session,
            user_id=user.id,
            skill_slug=assignment.topic,
            domain=SkillDomain.PYTHON,
            weight=WEIGHT_SOLUTION_OPEN,
            meta={"assignmentId": assignment.id},
        )
        await session.flush()
    return {"source": ref.source, "note": ref.note}


# --- комментарий к сдаче (§5.3) + низкая усилийность + события


async def _make_comment(
    session: AsyncSession, redis, user: User, assignment: PyAssignment, grade, code: str
) -> tuple[str, str, str, str] | None:
    """Комментарий по маршруту comment (L1/L2 по уровню); echo — dev.

    Возвращает (route, model_used, level, content) или None (шлюз недоступен).
    RAG-контекст по теме задания — блок knowledge (S-14).
    """
    level = await _user_level(session, user)
    knowledge = await _rag_knowledge(session, assignment.topic, level)
    messages = build_messages(
        "python_teacher.comment",
        level,
        request=f"Прокомментируй решение ученика задания «{assignment.title}».",
        user_input=f"Код ученика:\n{code[:2000]}",
        facts=[
            f"Вердикт: {grade.verdict}",
            f"Тесты: {grade.passed_tests}/{grade.total_tests}",
            (
                f"Первый проваленный тест: №{grade.failed_test}"
                if grade.failed_test is not None
                else "Все тесты пройдены"
            ),
        ],
        knowledge=knowledge,
    )
    try:
        result = await llm_generate(
            session,
            redis,
            route="python_teacher.comment",
            level=level,
            messages=messages,
            ctx=LLMCallContext(user_id=user.id, billing_tier=await _user_tier(session, user)),
        )
    except Exception as exc:  # noqa: BLE001 — комментарий не ломает сдачу
        logger.warning("py: комментарий не получен: %s", exc)
        return None
    return result.route, result.model_used, level.value, result.text


async def submit(
    session: AsyncSession,
    redis,
    user: User,
    assignment_id: int,
    code: str,
    request: Request | None = None,
) -> tuple[PySubmission, object]:
    """Сдача: прогон в песочнице → вердикт → py_submissions → комментарий →
    low_effort-флаг → событие навыка (Design §5.3)."""
    assignment = await get_assignment(session, assignment_id)
    attempt_no = (
        int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(PySubmission)
                    .where(
                        PySubmission.user_id == user.id,
                        PySubmission.assignment_id == assignment.id,
                    )
                )
            ).scalar_one()
        )
        + 1
    )
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

    # комментарий (LLM-шлюз; echo в dev)
    comment = await _make_comment(session, redis, user, assignment, grade, code)
    if comment is not None:
        route, model_used, level_value, content = comment
        session.add(
            PyFeedback(
                submission_id=submission.id,
                user_id=user.id,
                route=route,
                model_used=model_used,
                level=level_value,
                content=content,
            )
        )
        await session.flush()

    # античит: low_effort (флаги не блокируют — §9.1)
    await check_low_effort(
        session,
        user_id=user.id,
        submission_id=submission.id,
        code=code,
        starter_code=assignment.starter_code,
        attempt_no=attempt_no,
    )
    # античит: plagiarism (сходство с эталоном/сверстниками, S-24)
    from domains.anticheat.similarity import check_plagiarism

    await check_plagiarism(
        session,
        user_id=user.id,
        submission_id=submission.id,
        assignment_id=assignment.id,
        code=code,
    )

    # событие навыка (тема задания; вес меньше при неудаче — §5.3)
    if user.role is UserRole.STUDENT:
        weight = WEIGHT_SUBMIT_PASSED if grade.verdict == "passed" else WEIGHT_SUBMIT_FAILED
        await emit_skill_event(
            session,
            user_id=user.id,
            skill_slug=assignment.topic,
            domain=SkillDomain.PYTHON,
            weight=weight,
            meta={"submissionId": submission.id, "verdict": grade.verdict},
        )
        await session.flush()
        if grade.verdict == "passed":
            await record_passed_solution(
                session,
                user,
                assignment.topic,
                assignment.id,
                request=request,
            )
        else:
            from domains.review import service as review_svc

            await review_svc.create_from_python(
                session,
                user.id,
                assignment_id=assignment.id,
                assignment_title=assignment.title,
                topic=assignment.topic,
                failed_test=grade.failed_test,
            )

    logger.info(
        "py: сдача user_id=%s assignment=%s → %s (%d/%d)",
        user.id, assignment.slug, grade.verdict, grade.passed_tests, grade.total_tests,
    )
    return submission, grade


async def get_feedback(
    session: AsyncSession, submission_id: int
) -> PyFeedback | None:
    return (
        await session.execute(
            select(PyFeedback).where(PyFeedback.submission_id == submission_id)
        )
    ).scalar_one_or_none()


def resolve_level_or_none(value: str | None) -> AssignmentLevel | None:
    if value is None:
        return None
    try:
        return AssignmentLevel(value.strip().lower())
    except ValueError:
        raise AppError(
            "invalid_level", "Уровень: novice | intermediate | advanced", 422
        ) from None
