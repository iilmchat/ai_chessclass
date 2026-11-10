"""Бизнес-логика профиля (Design §4.3): ensure/update/list/set_level."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.authz import teacher_student_ids
from core.errors import AppError
from core.levels import Level
from domains.auth.models import User, UserRole
from domains.profile.models import AgeGroup, UserProfile

logger = logging.getLogger(__name__)


async def ensure_profile(session: AsyncSession, user_id: int) -> UserProfile:
    """Профиль создаётся при первом обращении (страховка регистрации)."""
    profile = await session.get(UserProfile, user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id)
        session.add(profile)
        await session.flush()
        logger.info("profile: создан профиль для user_id=%s", user_id)
    return profile


async def get_profile_view(session: AsyncSession, user_id: int) -> tuple[User, UserProfile]:
    """Пользователь + профиль (для /profile/me и /profile/{id})."""
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("user_not_found", "Пользователь не найден", 404)
    profile = await ensure_profile(session, user.id)
    return user, profile


async def update_my_profile(
    session: AsyncSession,
    user_id: int,
    display_name: str | None,
    prefs: dict | None,
    age_group: AgeGroup | None = None,
) -> UserProfile:
    """PATCH /profile/me: display_name/prefs/age_group; level здесь не меняется."""
    profile = await ensure_profile(session, user_id)
    if display_name is not None:
        profile.display_name = display_name
    if prefs is not None:
        profile.prefs = prefs
    if age_group is not None:
        # S-83: self-declared изменение возраста делает подтверждение учителя
        # устаревшим — сбрасываем trusted-метку до следующего подтверждения.
        if profile.age_group != age_group:
            profile.age_group_confirmed_at = None
            profile.age_group_confirmed_by = None
        profile.age_group = age_group
    await session.flush()
    return profile


async def set_user_level(session: AsyncSession, user_id: int, level: Level) -> UserProfile:
    """Смена уровня — только admin (Design §12.2)."""
    profile = await ensure_profile(session, user_id)
    old = profile.level
    profile.level = level
    await session.flush()
    logger.info("profile: user_id=%s level %s → %s", user_id, old, level)
    return profile


async def list_students(
    session: AsyncSession, viewer: User, page: int, page_size: int
) -> tuple[list[tuple[User, UserProfile]], int]:
    """S-91: admin — все ученики; teacher — только ученики своих классов."""
    filters = [User.role == UserRole.STUDENT]
    if viewer.role is UserRole.TEACHER:
        filters.append(User.id.in_(teacher_student_ids(viewer.id)))
    total = (
        await session.execute(
            select(func.count()).select_from(User).where(*filters)
        )
    ).scalar_one()
    stmt = (
        select(User, UserProfile)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .where(*filters)
        .order_by(User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()
    return list(rows), int(total)
