"""Admin-роутер античита (Design §12.2): лента флагов + review."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from core.base import CamelModel
from domains.anticheat.models import AnticheatFlag
from domains.audit import service as audit_svc
from domains.auth.deps import CurrentUser, DbSession, require_role, require_scope
from domains.auth.models import User, UserRole

router = APIRouter(prefix="/admin/anticheat", tags=["anticheat"])

TeacherOrAdmin = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]
AuditorOrTeacher = Annotated[User, Depends(require_scope("flags"))]


class FlagOut(CamelModel):
    id: str
    userId: str
    kind: str
    domain: str
    sourceRef: str | None
    confidence: float
    evidence: dict
    status: str
    note: str | None


class FlagReviewIn(CamelModel):
    status: str = Field(pattern=r"^(reviewed|false_positive|confirmed)$")
    note: str | None = Field(default=None, max_length=1000)


@router.get("/flags", response_model=list[FlagOut])
async def list_flags(
    _guard: AuditorOrTeacher,
    session: DbSession,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[FlagOut]:
    from sqlalchemy import select

    from domains.anticheat.models import AnticheatFlag

    stmt = select(AnticheatFlag).order_by(AnticheatFlag.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(AnticheatFlag.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        FlagOut(
            id=str(f.id),
            userId=str(f.user_id),
            kind=f.kind.value,
            domain=f.domain.value,
            sourceRef=f.source_ref,
            confidence=float(f.confidence),
            evidence=f.evidence,
            status=f.status.value,
            note=f.note,
        )
        for f in rows
    ]


@router.post("/flags/{flag_id}/review", response_model=FlagOut)
async def review_flag(
    flag_id: int,
    body: FlagReviewIn,
    reviewer: TeacherOrAdmin,
    session: DbSession,
    request: Request,
) -> FlagOut:
    from datetime import UTC, datetime

    from domains.anticheat.models import FlagStatus

    flag = await session.get(AnticheatFlag, flag_id)
    if flag is None:
        from core.errors import AppError

        raise AppError("flag_not_found", "Флаг не найден", 404)
    flag.status = FlagStatus(body.status)
    flag.reviewed_by = reviewer.id
    flag.reviewed_at = datetime.now(UTC)
    flag.note = body.note
    await session.flush()
    await audit_svc.record(
        session,
        reviewer,
        "anticheat.flag.review",
        target_type="flag",
        target_id=flag.id,
        meta={"status": body.status, "note": body.note},
        request=request,
    )
    return FlagOut(
        id=str(flag.id),
        userId=str(flag.user_id),
        kind=flag.kind.value,
        domain=flag.domain.value,
        sourceRef=flag.source_ref,
        confidence=float(flag.confidence),
        evidence=flag.evidence,
        status=flag.status.value,
        note=flag.note,
    )


# --- judge-сессии (S-23)


class JudgeStartIn(CamelModel):
    sourceRef: str = Field(min_length=3, max_length=64)
    question: str = Field(min_length=5, max_length=2000)
    studentCode: str | None = Field(default=None, max_length=8000)


class JudgeSessionOut(CamelModel):
    id: str
    question: str
    answer: str
    modelUsed: str


class JudgeReviewIn(CamelModel):
    verdict: str = Field(min_length=3, max_length=2000)


@router.post("/judge", status_code=201, response_model=JudgeSessionOut)
async def start_judge(
    body: JudgeStartIn, user: CurrentUser, session: DbSession, request: Request
) -> JudgeSessionOut:
    """Ученик объясняет свой код — judge задаёт уточняющие вопросы (S-23)."""
    from domains.anticheat.judge import start_judge_session

    result = await start_judge_session(
        session,
        request.app.state.redis,
        user,
        source_ref=body.sourceRef,
        question=body.question,
        student_code=body.studentCode,
    )
    return JudgeSessionOut(
        id=str(result["sessionId"]),
        question=result["question"],
        answer=result["answer"],
        modelUsed=result["modelUsed"],
    )


@router.get("/judge", response_model=list[dict])
async def list_judge_sessions(
    _guard: AuditorOrTeacher,
    session: DbSession,
    user_id: int | None = Query(default=None, alias="userId"),
) -> list[dict]:
    from domains.anticheat.judge import list_sessions

    rows = await list_sessions(session, _guard, user_id=user_id)
    return [
        {
            "id": str(s.id),
            "userId": str(s.user_id),
            "sourceRef": s.source_ref,
            "question": s.question,
            "answer": s.answer,
            "modelUsed": s.model_used,
            "teacherVerdict": s.teacher_verdict,
        }
        for s in rows
    ]


@router.post("/judge/{session_id}/verdict", response_model=JudgeSessionOut)
async def review_judge_session(
    session_id: int,
    body: JudgeReviewIn,
    _guard: TeacherOrAdmin,
    session: DbSession,
    request: Request,
) -> JudgeSessionOut:
    from domains.anticheat.judge import review_session

    judge_session = await review_session(session, _guard, session_id, body.verdict)
    await audit_svc.record(
        session,
        _guard,
        "anticheat.judge.verdict",
        target_type="judge_session",
        target_id=session_id,
        meta={"verdict": body.verdict[:500]},
        request=request,
    )
    return JudgeSessionOut(
        id=str(judge_session.id),
        question=judge_session.question,
        answer=judge_session.answer,
        modelUsed=judge_session.model_used,
    )


class StudentCardOut(CamelModel):
    userId: str
    email: str
    flags: list[FlagOut]
    judgeSessions: list[dict]


@router.get("/students/{user_id}/card", response_model=StudentCardOut)
async def student_card(
    user_id: int, _guard: AuditorOrTeacher, session: DbSession
) -> StudentCardOut:
    """Карточка ученика: лента флагов + judge-сессии (кабинет учителя, S-24)."""
    from sqlalchemy import select

    from domains.anticheat.judge import list_sessions
    from domains.auth.models import User

    student = await session.get(User, user_id)
    if student is None:
        from core.errors import AppError

        raise AppError("user_not_found", "Ученик не найден", 404)
    flags = (
        await session.execute(
            select(AnticheatFlag)
            .where(AnticheatFlag.user_id == user_id)
            .order_by(AnticheatFlag.confidence.desc())
            .limit(50)
        )
    ).scalars().all()
    sessions_list = await list_sessions(session, _guard, user_id=user_id, limit=20)
    return StudentCardOut(
        userId=str(user_id),
        email=student.email,
        flags=[
            FlagOut(
                id=str(f.id),
                userId=str(f.user_id),
                kind=f.kind.value,
                domain=f.domain.value,
                sourceRef=f.source_ref,
                confidence=float(f.confidence),
                evidence=f.evidence,
                status=f.status.value,
                note=f.note,
            )
            for f in flags
        ],
        judgeSessions=[
            {
                "id": str(s.id),
                "sourceRef": s.source_ref,
                "question": s.question,
                "answer": s.answer,
                "teacherVerdict": s.teacher_verdict,
            }
            for s in sessions_list
        ],
    )
