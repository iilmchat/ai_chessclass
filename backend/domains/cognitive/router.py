"""Роутер /api/v1/skills (Design §12.2): срез навыков, легенда, перекалькуляция."""

from typing import Annotated

from fastapi import APIRouter, Depends

from core.base import CamelModel
from domains.auth.deps import CurrentUser, DbSession, require_role
from domains.auth.models import User, UserRole
from domains.cognitive import service as svc

router = APIRouter(prefix="/skills", tags=["cognitive"])

TeacherOrAdmin = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]


class SkillScoreOut(CamelModel):
    slug: str
    titleRu: str
    domain: str
    score: float
    week: str | None


class SkillSnapshotOut(CamelModel):
    userId: str
    skills: list[SkillScoreOut]
    recommendations: list[dict]


class LegendOut(CamelModel):
    skills: list[SkillScoreOut]


class RecalcOut(CamelModel):
    userId: str
    updatedRows: int


@router.get("/me", response_model=SkillSnapshotOut)
async def my_skills(user: CurrentUser, session: DbSession) -> SkillSnapshotOut:
    skills = await svc.scores_snapshot(session, user.id)
    recommendations = await svc.recommendations(session, user.id)
    return SkillSnapshotOut(
        userId=str(user.id),
        skills=[SkillScoreOut(**s) for s in skills],
        recommendations=recommendations,
    )


@router.get("/legend", response_model=LegendOut)
async def legend(session: DbSession, _user: CurrentUser) -> LegendOut:
    """Легенда реестра (без скор): для описания навыков в UI."""
    snapshot = await svc.scores_snapshot(session, user_id=0)
    return LegendOut(skills=[SkillScoreOut(**s) for s in snapshot])


@router.get("/{user_id}", response_model=SkillSnapshotOut)
async def user_skills(
    user_id: int, _guard: TeacherOrAdmin, session: DbSession
) -> SkillSnapshotOut:
    skills = await svc.scores_snapshot(session, user_id)
    recommendations = await svc.recommendations(session, user_id)
    return SkillSnapshotOut(
        userId=str(user_id),
        skills=[SkillScoreOut(**s) for s in skills],
        recommendations=recommendations,
    )


@router.post("/{user_id}/recalc", response_model=RecalcOut)
async def recalc_user(
    user_id: int, _guard: TeacherOrAdmin, session: DbSession
) -> RecalcOut:
    updated = await svc.recalc_user_scores(session, user_id)
    await session.commit()
    return RecalcOut(userId=str(user_id), updatedRows=updated)
