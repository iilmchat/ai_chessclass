"""Роутер /api/v1/progress (S-42): прогресс, стрики, бейджи."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from core.base import CamelModel
from domains.auth.deps import CurrentUser, DbSession, require_role
from domains.auth.models import User, UserRole
from domains.progress import service as svc

router = APIRouter(prefix="/progress", tags=["progress"])

TeacherOrAdmin = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]


class AchievementOut(CamelModel):
    code: str
    title_ru: str
    description: str
    icon: str
    awarded: bool
    awarded_at: datetime | None


class ProgressOut(CamelModel):
    user_id: str
    solved_count: int
    topics: dict[str, int]
    current_streak: int
    longest_streak: int
    last_solved_on: date | None
    achievements: list[AchievementOut]


@router.get("/me", response_model=ProgressOut)
async def my_progress(user: CurrentUser, session: DbSession) -> ProgressOut:
    return ProgressOut(**await svc.get_progress(session, user.id))


@router.get("/{user_id}", response_model=ProgressOut)
async def user_progress(
    user_id: int, _guard: TeacherOrAdmin, session: DbSession
) -> ProgressOut:
    return ProgressOut(**await svc.get_progress(session, user_id))
