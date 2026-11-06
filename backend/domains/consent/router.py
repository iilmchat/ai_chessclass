"""Роутер /api/v1/consent (S-74, ADR-019): parental consent workflow."""

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.base import CamelModel
from core.config import settings
from core.email import parental_consent_email
from core.errors import AppError
from core.ratelimit import enforce_rate_limit
from domains.audit import service as audit_svc
from domains.auth.deps import CurrentUser, DbSession
from domains.consent import service as svc
from domains.notifications import service as notifications_svc

router = APIRouter(prefix="/consent", tags=["consent"])


class ConsentStatusOut(CamelModel):
    required: bool
    status: str
    policy_version: str
    # S-83: возрастная группа и подтверждение учителем (consent enforcement).
    age_group: str
    teacher_confirmed: bool
    age_group_confirmed_at: str | None
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
    email_delivered: bool = False
    # S-83: письмо не доставлено сразу — поставлено в email_outbox и будет
    # повторено cron-задачей `email_outbox_deliver`.
    email_queued: bool = False


class ConsentConfirmIn(CamelModel):
    token: str = Field(min_length=16, max_length=256)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _out(state: svc.ConsentState) -> ConsentStatusOut:
    return ConsentStatusOut(
        required=state.required,
        status=state.status,
        policy_version=state.policy_version,
        age_group=state.age_group,
        teacher_confirmed=state.teacher_confirmed,
        age_group_confirmed_at=_iso(state.age_group_confirmed_at),
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


async def _enqueue_parent_email(
    session: AsyncSession,
    parent_email: str,
    link: str,
    policy_version: str,
) -> bool:
    """S-83: письмо родителю — через email_outbox (retry/backoff).

    True — строка доставлена сейчас (SMTP или dev-консоль); False — осталась
    в очереди на повтор cron-задачей `email_outbox_deliver`.
    """
    subject, text = parental_consent_email(link, policy_version)
    row = await notifications_svc.enqueue(
        session,
        to=parent_email,
        subject=subject,
        body=text,
        kind="parental_consent",
    )
    delivered = await notifications_svc.deliver_one(session, row)
    # dev-консоль: transport вернул False, но строка помечена `sent` — это не
    # очередь на retry, письмо уже записано в лог.
    return delivered or row.status == "sent"


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
    delivered = await _enqueue_parent_email(
        session, row.parent_email, link, row.policy_version
    )
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
        email_delivered=delivered,
        email_queued=not delivered,
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
