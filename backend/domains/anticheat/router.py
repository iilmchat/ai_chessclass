"""Admin-роутер античита (Design §12.2): лента флагов + review."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from core.base import CamelModel
from domains.anticheat.models import AnticheatFlag
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole

router = APIRouter(prefix="/admin/anticheat", tags=["anticheat"])

TeacherOrAdmin = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]


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
    _guard: TeacherOrAdmin,
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
