"""Роутер /api/v1/profile (Design §12.2): me / students / set-level.

RBAC: свой профиль — все; профиль ученика и список — teacher/admin;
смена уровня — только admin. Пагинация (Design §12.1, с S-03): page/pageSize.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from domains.auth.deps import CurrentUser, DbSession, require_role
from domains.auth.models import User, UserRole
from domains.auth.schemas import user_out
from domains.profile import service as svc
from domains.profile.models import UserProfile
from domains.profile.schemas import LevelUpdateIn, PageOut, ProfileOut, ProfileUpdateIn

router = APIRouter(prefix="/profile", tags=["profile"])

TeacherOrAdmin = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]
AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]


def _profile_out(user: User, profile: UserProfile | None) -> ProfileOut:
    base = user_out(user).model_dump()
    return ProfileOut(
        **base,
        displayName=profile.display_name if profile else None,
        level=profile.level if profile else None,
        billingTier=profile.billing_tier if profile else None,
        prefs=profile.prefs if profile else {},
    )


@router.get("/me", response_model=ProfileOut)
async def get_me(user: CurrentUser, session: DbSession) -> ProfileOut:
    _, profile = await svc.get_profile_view(session, user.id)
    return _profile_out(user, profile)


@router.patch("/me", response_model=ProfileOut)
async def patch_me(
    body: ProfileUpdateIn, user: CurrentUser, session: DbSession
) -> ProfileOut:
    profile = await svc.update_my_profile(
        session, user.id, body.display_name, body.prefs
    )
    return _profile_out(user, profile)


@router.get("/students", response_model=PageOut)
async def get_students(
    session: DbSession,
    _guard: TeacherOrAdmin,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
) -> PageOut:
    rows, total = await svc.list_students(session, page, page_size)
    items = [_profile_out(user, profile) for user, profile in rows]
    return PageOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{user_id}", response_model=ProfileOut)
async def get_profile(
    user_id: int, session: DbSession, _guard: TeacherOrAdmin
) -> ProfileOut:
    user, profile = await svc.get_profile_view(session, user_id)
    return _profile_out(user, profile)


@router.patch("/{user_id}/level", response_model=ProfileOut)
async def set_level(
    user_id: int, body: LevelUpdateIn, session: DbSession, _guard: AdminOnly
) -> ProfileOut:
    user, _profile = await svc.get_profile_view(session, user_id)
    profile = await svc.set_user_level(session, user_id, body.level)
    return _profile_out(user, profile)
