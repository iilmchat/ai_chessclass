"""Роутер /api/v1/consent (S-74, ADR-019): parental consent workflow."""

import logging
from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import EmailStr, Field

from core.base import CamelModel
from core.config import settings
from core.errors import AppError
from core.ratelimit import enforce_rate_limit
from domains.audit import service as audit_svc
from domains.auth.deps import CurrentUser, DbSession
from domains.consent import service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/consent", tags=["consent"])


class ConsentStatusOut(CamelModel):
    required: bool
    status: str
    policy_version: str
    parent_email: EmailStr | None
    requested_at: str | None
    confirmed_at: str | None
    revoked_at: str | None
    expires_at: str | None


class ConsentRequestIn(CamelModel):
    parent_email: EmailStr


class ConsentRequestOut(ConsentStatusOut):
    dev_token: str | None = None
    confirm_url: str | None = None


class ConsentConfirmIn(CamelModel):
    token: str = Field(min_length=16, max_length=256)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _out(state: svc.ConsentState) -> ConsentStatusOut:
    return ConsentStatusOut(
        required=state.required,
        status=state.status,
        policy_version=state.policy_version,
        parent_email=state.parent_email,
        requested_at=_iso(state.requested_at),
        confirmed_at=_iso(state.confirmed_at),
        revoked_at=_iso(state.revoked_at),
        expires_at=_iso(state.expires_at),
    )


def _redis(request: Request):
    client = getattr(request.app.state, "redis", None)
    if client is None:
        raise AppError("internal_error", "Redis недоступен", 500)
    return client


def _send_parent_email(parent_email: str, link: str) -> None:
    """Dev-транспорт; в prod подключается SMTP (как verify-email)."""
    logger.info(
        "[dev-email] to=%s kind=parental-consent link=%s", parent_email, link
    )


@router.get("/status", response_model=ConsentStatusOut)
async def get_status(user: CurrentUser, session: DbSession) -> ConsentStatusOut:
    return _out(await svc.get_state(session, user.id))


@router.post("/request", response_model=ConsentRequestOut)
async def request_consent(
    body: ConsentRequestIn,
    user: CurrentUser,
    session: DbSession,
    request: Request,
) -> ConsentRequestOut:
    await enforce_rate_limit(
        _redis(request), f"consent:{user.id}", limit=5, window_s=3600
    )
    row, raw = await svc.request_consent(session, user.id, str(body.parent_email))
    link = svc.confirm_url(raw)
    _send_parent_email(row.parent_email, link)
    await audit_svc.record(
        session,
        user,
        "consent.request",
        target_type="user",
        target_id=user.id,
        request=request,
        meta={"policyVersion": row.policy_version},
    )
    await session.commit()
    state = await svc.get_state(session, user.id)
    dev = settings.app_env == "dev"
    return ConsentRequestOut(
        **_out(state).model_dump(),
        dev_token=raw if dev else None,
        confirm_url=link if dev else None,
    )


@router.post("/confirm", response_model=ConsentStatusOut)
async def confirm_consent(
    body: ConsentConfirmIn, session: DbSession, request: Request
) -> ConsentStatusOut:
    row = await svc.confirm_consent(session, body.token)
    state = await svc.get_state(session, row.user_id)
    await audit_svc.record(
        session,
        None,
        "consent.granted",
        target_type="user",
        target_id=row.user_id,
        request=request,
        meta={"policyVersion": row.policy_version},
    )
    await session.commit()
    return _out(state)


@router.post("/revoke", response_model=ConsentStatusOut)
async def revoke_consent(
    user: CurrentUser, session: DbSession, request: Request
) -> ConsentStatusOut:
    state = await svc.revoke_consent(session, user.id)
    await audit_svc.record(
        session,
        user,
        "consent.revoked",
        target_type="user",
        target_id=user.id,
        request=request,
    )
    await session.commit()
    return _out(state)
