"""Роутер /api/v1/py (Design §12.2): задания, сдача, вердикты.

Тесты задания ученику не отдаём (только количество) — admin видит всё.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from core.base import PageOut
from domains.auth.deps import CurrentUser, DbSession, require_role
from domains.auth.models import User, UserRole
from domains.python_teacher import service as svc
from domains.python_teacher.models import PyAssignment, PySubmission
from domains.python_teacher.schemas import (
    AssignmentCreateIn,
    AssignmentDetailOut,
    AssignmentOut,
    AssignmentUpdateIn,
    SubmissionOut,
    SubmitIn,
)

router = APIRouter(prefix="/py", tags=["python_teacher"])

AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]


def _out(assignment: PyAssignment) -> AssignmentOut:
    return AssignmentOut(
        id=str(assignment.id),
        slug=assignment.slug,
        title=assignment.title,
        level=assignment.level,
        topic=assignment.topic,
        tests_count=len(assignment.tests),
    )


def _detail_out(assignment: PyAssignment, include_tests: bool) -> AssignmentDetailOut:
    return AssignmentDetailOut(
        id=str(assignment.id),
        slug=assignment.slug,
        title=assignment.title,
        level=assignment.level,
        topic=assignment.topic,
        tests_count=len(assignment.tests),
        statement=assignment.statement,
        starter_code=assignment.starter_code,
        tests=[str(t) for t in assignment.tests] if include_tests else None,
        checkpoints=list(assignment.checkpoints) if include_tests else None,
        is_active=assignment.is_active if include_tests else None,
    )


def _submission_out(submission: PySubmission) -> SubmissionOut:
    return SubmissionOut(
        id=str(submission.id),
        assignment_id=str(submission.assignment_id),
        verdict=submission.verdict,
        passed_tests=submission.passed_tests,
        total_tests=submission.total_tests,
        failed_test=submission.failed_test,
        stdout_digest=submission.stdout_digest,
        duration_ms=submission.duration_ms,
        created_at=submission.created_at,
    )


@router.get("/assignments", response_model=PageOut)
async def list_assignments(
    user: CurrentUser,
    session: DbSession,
    level: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100, alias="pageSize"),
) -> PageOut:
    parsed_level = svc.resolve_level_or_none(level)
    rows, total = await svc.list_assignments(session, parsed_level, page, page_size)
    return PageOut(items=[_out(a) for a in rows], total=total, page=page, page_size=page_size)


@router.post("/assignments", status_code=201, response_model=AssignmentDetailOut)
async def create_assignment(
    body: AssignmentCreateIn, _guard: AdminOnly, session: DbSession
) -> AssignmentDetailOut:
    assignment = await svc.create_assignment(
        session,
        slug=body.slug,
        title=body.title,
        level=body.level,
        topic=body.topic,
        statement=body.statement,
        starter_code=body.starter_code,
        tests=body.tests,
        hints=[h.model_dump() for h in (body.hints or [])],
    )
    return _detail_out(assignment, include_tests=True)


@router.get("/assignments/{assignment_id}", response_model=AssignmentDetailOut)
async def get_assignment(
    assignment_id: int, user: CurrentUser, session: DbSession
) -> AssignmentDetailOut:
    assignment = await svc.get_assignment(session, assignment_id)
    include_tests = user.role in (UserRole.TEACHER, UserRole.ADMIN)
    return _detail_out(assignment, include_tests=include_tests)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentDetailOut)
async def update_assignment(
    assignment_id: int,
    body: AssignmentUpdateIn,
    _guard: AdminOnly,
    session: DbSession,
) -> AssignmentDetailOut:
    assignment = await svc.update_assignment(
        session,
        assignment_id,
        title=body.title,
        level=body.level,
        statement=body.statement,
        starter_code=body.starter_code,
        tests=body.tests,
    )
    return _detail_out(assignment, include_tests=True)


@router.post("/assignments/{assignment_id}/submit", response_model=SubmissionOut)
async def submit(
    assignment_id: int, body: SubmitIn, user: CurrentUser, session: DbSession
) -> SubmissionOut:
    submission, _grade = await svc.submit(session, user, assignment_id, body.code)
    return _submission_out(submission)


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
async def get_submission(
    submission_id: int, user: CurrentUser, session: DbSession
) -> SubmissionOut:
    submission = await svc.get_submission(session, submission_id, user)
    return _submission_out(submission)
