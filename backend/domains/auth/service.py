"""Бизнес-логика auth (Design §13.1).

Регистрация → email-токен (24 ч, одноразовый); логин — Argon2id + проверка
верификации; refresh — opaque token, в БД только SHA-256, ротация при
использовании, при повторном использовании отозванного — отзыв всех сессий.
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from core.security import hash_password, parse_duration, verify_password
from domains.auth.models import EmailToken, EmailTokenKind, RefreshSession, User

logger = logging.getLogger(__name__)

EMAIL_TOKEN_TTL = timedelta(hours=24)  # Design §13.1


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    return (await session.execute(stmt)).scalar_one_or_none()


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    """Создание student-аккаунта; роль от клиента не принимается (порт teacher)."""
    if await get_user_by_email(session, email) is not None:
        raise AppError("auth_email_taken", "Email уже зарегистрирован", 409)
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:  # гонка регистраций на одном email
        raise AppError("auth_email_taken", "Email уже зарегистрирован", 409) from exc
    return user


async def issue_email_token(
    session: AsyncSession, user: User, kind: EmailTokenKind
) -> str:
    """Одноразовый токен (24 ч); предыдущие того же типа гасятся."""
    await session.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user.id,
            EmailToken.kind == kind,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=_now())
    )
    raw = secrets.token_urlsafe(32)
    session.add(
        EmailToken(
            user_id=user.id,
            kind=kind,
            token=raw,
            expires_at=_now() + EMAIL_TOKEN_TTL,
        )
    )
    await session.flush()
    return raw


async def _consume_email_token(
    session: AsyncSession, token: str, kind: EmailTokenKind
) -> User:
    stmt = select(EmailToken).where(
        EmailToken.token == token, EmailToken.kind == kind
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    now = _now()
    if row is None or row.used_at is not None or row.expires_at < now:
        raise AppError("auth_invalid_token", "Токен недействителен или истёк", 401)
    user = await session.get(User, row.user_id)
    if user is None:
        raise AppError("auth_invalid_token", "Пользователь не найден", 401)
    row.used_at = now
    return user


async def verify_email(session: AsyncSession, token: str) -> User:
    user = await _consume_email_token(session, token, EmailTokenKind.VERIFY)
    user.email_verified_at = _now()
    await session.flush()
    return user


async def authenticate_user(
    session: AsyncSession, email: str, password: str
) -> User:
    user = await get_user_by_email(session, email)
    if user is None or not verify_password(password, user.password_hash):
        raise AppError("auth_invalid_credentials", "Неверный email или пароль", 401)
    if user.email_verified_at is None:
        raise AppError("auth_email_not_verified", "Email не подтверждён", 403)
    if not user.is_active:
        raise AppError("auth_inactive", "Аккаунт деактивирован", 403)
    return user


async def create_refresh_session(
    session: AsyncSession, user: User, user_agent: str | None
) -> str:
    raw = secrets.token_urlsafe(48)
    session.add(
        RefreshSession(
            user_id=user.id,
            token_hash=_hash_token(raw),
            user_agent=(user_agent or "")[:512] or None,
            expires_at=_now() + parse_duration(settings.refresh_ttl),
        )
    )
    await session.flush()
    return raw


async def rotate_refresh_session(
    session: AsyncSession, raw_token: str, user_agent: str | None
) -> tuple[User, str]:
    """Ротация: старая сессия отзывается, выдаётся новая (Design §13.1).

    Повторное использование отозванного токена → отзыв всех сессий
    пользователя (защита от кражи cookie).
    """
    stmt = select(RefreshSession).where(
        RefreshSession.token_hash == _hash_token(raw_token)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    now = _now()
    if row is None or row.expires_at < now:
        raise AppError("auth_invalid_refresh", "Refresh-токен недействителен", 401)
    if row.revoked_at is not None:
        await session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.user_id == row.user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        # ВАЖНО: commit до raise — иначе get_session откатит отзыв вместе
        # с 401 (AppError), и «отозванные» сессии останутся валидными.
        await session.commit()
        logger.warning(
            "auth: reuse отозванного refresh-токена user_id=%s — все сессии отозваны",
            row.user_id,
        )
        raise AppError("auth_invalid_refresh", "Refresh-токен отозван", 401)
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AppError("auth_invalid_refresh", "Пользователь недоступен", 401)
    row.revoked_at = now
    new_raw = await create_refresh_session(session, user, user_agent)
    return user, new_raw


async def revoke_refresh_session(session: AsyncSession, raw_token: str) -> None:
    await session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.token_hash == _hash_token(raw_token),
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )


async def request_password_reset(
    session: AsyncSession, email: str
) -> tuple[User, str] | None:
    """Токен сброса только для верифицированных; иначе — тишина (не раскрываем)."""
    user = await get_user_by_email(session, email)
    if user is None or user.email_verified_at is None:
        return None
    raw = await issue_email_token(session, user, EmailTokenKind.RESET)
    return user, raw


async def confirm_password_reset(
    session: AsyncSession, token: str, new_password: str
) -> User:
    user = await _consume_email_token(session, token, EmailTokenKind.RESET)
    user.password_hash = hash_password(new_password)
    await session.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await session.flush()
    return user
