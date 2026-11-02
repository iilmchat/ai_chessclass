"""FastAPI-зависимости auth: текущий пользователь, роли (порт teacher).

admin проходит любую роль (как в teacher require_role).
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.errors import AppError
from core.security import decode_token
from domains.auth.models import User, UserRole

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_session)]


def _unauthorized(detail: str = "Требуется авторизация") -> AppError:
    return AppError("auth_unauthorized", detail, 401)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise _unauthorized()
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise _unauthorized("Access-токен недействителен")
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.isdigit():
        raise _unauthorized()
    user = await session.get(User, int(sub))
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(
    *allowed: UserRole,
) -> Callable[..., Awaitable[User]]:
    """Фабрика зависимостей: роль из allowed; admin проходит всегда."""

    async def checker(user: CurrentUser) -> User:
        if user.role not in allowed and user.role is not UserRole.ADMIN:
            raise AppError("auth_forbidden", "Недостаточно прав", 403)
        return user

    return checker


def require_scope(scope: str) -> Callable[..., Awaitable[User]]:
    """RBAC + auditor scope (S-47).

    teacher/admin проходят всегда; auditor проверяется по
    `user_profiles.prefs["auditor_scope"]` (отсутствует → разрешено).
    """

    async def checker(user: CurrentUser, session: DbSession) -> User:
        if user.role in (UserRole.ADMIN, UserRole.TEACHER):
            return user
        if user.role is not UserRole.AUDITOR:
            raise AppError("auth_forbidden", "Недостаточно прав", 403)
        from domains.profile.models import UserProfile

        profile = await session.get(UserProfile, user.id)
        scopes = (profile.prefs or {}).get("auditor_scope", {}) if profile else {}
        if scopes.get(scope) is False:
            raise AppError(
                "auth_forbidden", f"Нет scope auditor: {scope}", 403
            )
        return user

    return checker
