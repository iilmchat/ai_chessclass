"""Роутер /api/v1/profile (Design §12.2): me / students / set-level.

RBAC: свой профиль — все; профиль ученика и список — teacher/admin;
смена уровня — только admin. Пагинация (Design §12.1, с S-03): page/pageSize.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from core.authz import ensure_can_access_student_data
from domains.audit import service as audit_svc
from domains.auth.deps import CurrentUser, DbSession, require_role
from domains.auth.models import User, UserRole
from domains.auth.schemas import user_out
from domains.profile import service as svc
from domains.profile.models import AgeGroup, UserProfile
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
        ageGroup=profile.age_group if profile else AgeGroup.UNKNOWN,
        prefs=profile.prefs if profile else {},
    )


@router.get("/me", response_model=ProfileOut)
async def get_me(user: CurrentUser, session: DbSession) -> ProfileOut:
    _, profile = await svc.get_profile_view(session, user.id)
    return _profile_out(user, profile)


@router.patch("/me", response_model=ProfileOut)
async def patch_me(
    body: ProfileUpdateIn,
    user: CurrentUser,
    session: DbSession,
    request: Request,
) -> ProfileOut:
    before = await svc.ensure_profile(session, user.id)
    old_age_group = before.age_group
    profile = await svc.update_my_profile(
        session, user.id, body.display_name, body.prefs, body.age_group
    )
    # S-83: self-declared смена возраста сбрасывает подтверждение учителя —
    # событие пишем в аудит (доказуемость consent enforcement).
    if body.age_group is not None and body.age_group != old_age_group:
        await audit_svc.record(
            session,
            user,
            "profile.age_group",
            target_type="user",
            target_id=user.id,
            meta={"from": old_age_group.value, "to": body.age_group.value},
            request=request,
        )
    return _profile_out(user, profile)


@router.get("/students", response_model=PageOut)
async def get_students(
    session: DbSession,
    _guard: TeacherOrAdmin,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
) -> PageOut:
    rows, total = await svc.list_students(session, _guard, page, page_size)
    items = [_profile_out(user, profile) for user, profile in rows]
    return PageOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{user_id}", response_model=ProfileOut)
async def get_profile(
    user_id: int, session: DbSession, _guard: TeacherOrAdmin
) -> ProfileOut:
    await ensure_can_access_student_data(_guard, user_id, session)
    user, profile = await svc.get_profile_view(session, user_id)
    return _profile_out(user, profile)


@router.patch("/{user_id}/level", response_model=ProfileOut)
async def set_level(
    user_id: int, body: LevelUpdateIn, session: DbSession, _guard: AdminOnly
) -> ProfileOut:
    user, _profile = await svc.get_profile_view(session, user_id)
    profile = await svc.set_user_level(session, user_id, body.level)
    return _profile_out(user, profile)
