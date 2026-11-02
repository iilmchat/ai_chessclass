"""Роутер этюдов (S-43): публичная лента/попытки + админ-ревью."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from core.base import CamelModel
from domains.auth.deps import CurrentUser, DbSession, require_role
from domains.auth.models import User, UserRole
from domains.studies import service as svc
from domains.studies.models import ChessStudy, StudyStatus

router = APIRouter(prefix="/studies", tags=["studies"])
admin_router = APIRouter(prefix="/admin/studies", tags=["studies"])

TeacherOrAdmin = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]
ReadRoles = Annotated[
    User,
    Depends(require_role(UserRole.TEACHER, UserRole.ADMIN, UserRole.AUDITOR)),
]


class StudyOut(CamelModel):
    id: str
    title: str
    fen: str
    condition_text: str
    theme: str
    difficulty: str
    status: str
    created_at: datetime


class StudyAdminOut(StudyOut):
    solution_uci: str
    solution_line: list[str]
    source: str
    generator_meta: dict
    created_by: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None


class StudyPageOut(CamelModel):
    items: list[StudyOut]
    total: int
    page: int
    page_size: int


class StudyAdminPageOut(CamelModel):
    items: list[StudyAdminOut]
    total: int
    page: int
    page_size: int


class ReviewIn(CamelModel):
    decision: str = Field(pattern=r"^(approve|reject)$")
    note: str | None = Field(default=None, max_length=1000)


class AttemptIn(CamelModel):
    move_uci: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")


class AttemptOut(CamelModel):
    correct: bool
    message: str
    next_uci: str | None


def _out(study: ChessStudy) -> StudyOut:
    return StudyOut(
        id=str(study.id),
        title=study.title,
        fen=study.fen,
        condition_text=study.condition_text,
        theme=study.theme,
        difficulty=study.difficulty,
        status=study.status.value,
        created_at=study.created_at,
    )


def _admin_out(study: ChessStudy) -> StudyAdminOut:
    base = _out(study).model_dump()
    return StudyAdminOut(
        **base,
        solution_uci=study.solution_uci,
        solution_line=list(study.solution_line or []),
        source=study.source,
        generator_meta=study.generator_meta or {},
        created_by=str(study.created_by) if study.created_by is not None else None,
        reviewed_by=str(study.reviewed_by) if study.reviewed_by is not None else None,
        reviewed_at=study.reviewed_at,
        review_note=study.review_note,
    )


@router.get("", response_model=StudyPageOut)
async def list_published(
    _user: CurrentUser,
    session: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
) -> StudyPageOut:
    rows, total = await svc.list_studies(
        session, status=StudyStatus.PUBLISHED, page=page, page_size=page_size
    )
    return StudyPageOut(
        items=[_out(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{study_id}", response_model=StudyOut)
async def get_study(
    study_id: int, _user: CurrentUser, session: DbSession
) -> StudyOut:
    return _out(await svc.get_published(session, study_id))


@router.post("/{study_id}/attempt", response_model=AttemptOut)
async def attempt(
    study_id: int,
    body: AttemptIn,
    user: CurrentUser,
    session: DbSession,
) -> AttemptOut:
    result = await svc.attempt_study(session, user, study_id, body.move_uci)
    return AttemptOut(**result)


@admin_router.get("", response_model=StudyAdminPageOut)
async def list_for_review(
    _guard: ReadRoles,
    session: DbSession,
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
) -> StudyAdminPageOut:
    parsed: StudyStatus | None = None
    if status is not None:
        try:
            parsed = StudyStatus(status)
        except ValueError as exc:
            from core.errors import AppError

            raise AppError("study_status_invalid", "Неизвестный статус", 422) from exc
    rows, total = await svc.list_studies(
        session, status=parsed, page=page, page_size=page_size
    )
    return StudyAdminPageOut(
        items=[_admin_out(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@admin_router.post("/generate", status_code=201, response_model=StudyAdminOut)
async def generate(
    teacher: TeacherOrAdmin,
    session: DbSession,
    request: Request,
) -> StudyAdminOut:
    study = await svc.generate_study(
        session, request.app.state.redis, teacher
    )
    await session.commit()
    return _admin_out(study)


@admin_router.post("/{study_id}/submit", response_model=StudyAdminOut)
async def submit(
    study_id: int, teacher: TeacherOrAdmin, session: DbSession
) -> StudyAdminOut:
    study = await svc.submit_for_review(session, teacher, study_id)
    await session.commit()
    return _admin_out(study)


@admin_router.post("/{study_id}/review", response_model=StudyAdminOut)
async def review(
    study_id: int,
    body: ReviewIn,
    teacher: TeacherOrAdmin,
    session: DbSession,
) -> StudyAdminOut:
    study = await svc.review_study(
        session,
        teacher,
        study_id,
        decision=body.decision,
        note=body.note,
    )
    await session.commit()
    return _admin_out(study)
