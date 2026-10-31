"""Роутер /api/v1/auth (Design §12.2): register/verify/login/refresh/logout/me.

Refresh — HttpOnly-cookie c path=/api/v1/auth; rate-limit — Redis (§13.1).
"""

import logging

from fastapi import APIRouter, Request, Response

from core.config import settings
from core.errors import AppError
from core.ratelimit import (
    enforce_rate_limit,
    is_locked_out,
    register_auth_failure,
)
from core.security import create_access_token, parse_duration
from domains.auth import service as svc
from domains.auth.deps import CurrentUser, DbSession
from domains.auth.models import EmailTokenKind
from domains.auth.schemas import (
    AuthOut,
    LoginIn,
    MessageOut,
    PasswordResetConfirmIn,
    PasswordResetIn,
    RegisterIn,
    RegisterOut,
    TokenOut,
    UserOut,
    VerifyIn,
    user_out,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = settings.refresh_cookie_name
COOKIE_PATH = "/api/v1/auth"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _redis(request: Request):
    client = getattr(request.app.state, "redis", None)
    if client is None:
        raise AppError("internal_error", "Redis недоступен", 500)
    return client


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        raw_token,
        max_age=int(parse_duration(settings.refresh_ttl).total_seconds()),
        httponly=True,
        secure=settings.app_env == "prod",  # dev — http://localhost
        samesite="lax",
        path=COOKIE_PATH,
    )


def _send_email(email: str, *, kind: str, token: str) -> None:
    """Dev: консольный SMTP-бэкенд (Design §13.1). Прод-SMTP — при появлении env."""
    path = "verify-email" if kind == "verify" else "reset-password"
    link = f"{settings.web_base_url}/{path}?token={token}"
    logger.info("[dev-email] to=%s kind=%s link=%s", email, kind, link)


def _access_token(user_id: int, role: str) -> str:
    return create_access_token(user_id, role)


@router.post("/register", status_code=201, response_model=RegisterOut)
async def register(
    body: RegisterIn, request: Request, session: DbSession
) -> RegisterOut:
    await enforce_rate_limit(
        _redis(request), f"register:{_client_ip(request)}", limit=10, window_s=60
    )
    user = await svc.register_user(session, body.email.strip().lower(), body.password)
    token = await svc.issue_email_token(session, user, EmailTokenKind.VERIFY)
    _send_email(user.email, kind="verify", token=token)
    return RegisterOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        emailVerified=False,
    )


@router.post("/verify", response_model=MessageOut)
async def verify_email(body: VerifyIn, session: DbSession) -> MessageOut:
    await svc.verify_email(session, body.token)
    return MessageOut(ok=True)


@router.post("/login", response_model=AuthOut)
async def login(
    body: LoginIn, request: Request, response: Response, session: DbSession
) -> AuthOut:
    redis = _redis(request)
    ip = _client_ip(request)
    if await is_locked_out(redis, ip):
        raise AppError(
            "auth_locked_out",
            "Слишком много неудачных попыток входа; подождите 10 минут",
            429,
        )
    try:
        user = await svc.authenticate_user(
            session, body.email.strip().lower(), body.password
        )
    except AppError as exc:
        if exc.code == "auth_invalid_credentials":
            await register_auth_failure(redis, ip)
        raise
    raw = await svc.create_refresh_session(
        session, user, request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, raw)
    return AuthOut(
        accessToken=_access_token(user.id, user.role.value),
        user=user_out(user),
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    request: Request, response: Response, session: DbSession
) -> TokenOut:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise AppError("auth_invalid_refresh", "Refresh-cookie отсутствует", 401)
    user, new_raw = await svc.rotate_refresh_session(
        session, raw, request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, new_raw)
    return TokenOut(accessToken=_access_token(user.id, user.role.value))


@router.post("/logout", response_model=MessageOut)
async def logout(
    request: Request, response: Response, session: DbSession
) -> MessageOut:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        await svc.revoke_refresh_session(session, raw)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return MessageOut(ok=True)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return user_out(user)


@router.post("/password-reset", status_code=202, response_model=MessageOut)
async def request_password_reset(
    body: PasswordResetIn, request: Request, session: DbSession
) -> MessageOut:
    await enforce_rate_limit(
        _redis(request), f"pwreset:{_client_ip(request)}", limit=5, window_s=60
    )
    result = await svc.request_password_reset(session, body.email.strip().lower())
    if result is not None:
        _user, token = result
        _send_email(body.email, kind="reset", token=token)
    # ответ одинаковый независимо от существования email
    return MessageOut(ok=True)


@router.post("/password-reset/confirm", response_model=MessageOut)
async def confirm_password_reset(
    body: PasswordResetConfirmIn, session: DbSession
) -> MessageOut:
    await svc.confirm_password_reset(session, body.token, body.new_password)
    return MessageOut(ok=True)
