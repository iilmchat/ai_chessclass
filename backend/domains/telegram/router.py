"""S-50: Telegram link/consent/status и код привязки."""

from fastapi import APIRouter, Request
from pydantic import Field

from core.base import CamelModel
from core.errors import AppError
from core.ratelimit import enforce_rate_limit
from domains.audit import service as audit_svc
from domains.auth.deps import CurrentUser, DbSession
from domains.telegram import service as svc
from domains.telegram.models import TelegramLink

router = APIRouter(prefix="/telegram", tags=["telegram"])


class LinkIn(CamelModel):
    chat_id: str = Field(min_length=5, max_length=32)
    consent: bool


class LinkOut(CamelModel):
    linked: bool
    consent: bool
    configured: bool


class LinkCodeOut(CamelModel):
    code: str
    deep_link: str
    expires_in_s: int


class ConfirmIn(CamelModel):
    code: str = Field(min_length=4, max_length=32)
    chat_id: str = Field(min_length=5, max_length=32)


class StatusOut(CamelModel):
    linked: bool
    consent: bool
    configured: bool
    counts: dict[str, int]


def _link_out(link: TelegramLink | None) -> LinkOut:
    from core.config import settings

    return LinkOut(
        linked=link is not None,
        consent=bool(link and link.consent),
        configured=bool(settings.telegram_bot_token),
    )


@router.get("/status", response_model=StatusOut)
async def telegram_status(user: CurrentUser, session: DbSession) -> StatusOut:
    return StatusOut(**await svc.status(session, user))


@router.post("/link", response_model=LinkOut)
async def link_telegram(
    body: LinkIn,
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> LinkOut:
    await enforce_rate_limit(
        request.app.state.redis,
        f"telegram-link:{user.id}",
        limit=5,
        window_s=60,
    )
    row = await svc.link(session, user, body.chat_id, body.consent)
    await audit_svc.record(
        session,
        user,
        "telegram.link",
        target_type="telegram",
        target_id=row.chat_id,
        request=request,
    )
    await session.commit()
    return _link_out(row)


@router.post("/link-code", response_model=LinkCodeOut)
async def link_code(
    request: Request, user: CurrentUser
) -> LinkCodeOut:
    await enforce_rate_limit(
        request.app.state.redis,
        f"telegram-code:{user.id}",
        limit=5,
        window_s=60,
    )
    from core.config import settings

    code, deep_link = await svc.make_link_code(
        request.app.state.redis, user.id
    )
    return LinkCodeOut(
        code=code,
        deep_link=deep_link,
        expires_in_s=settings.telegram_link_ttl_s,
    )


@router.post("/confirm", response_model=LinkOut)
async def confirm(
    body: ConfirmIn,
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> LinkOut:
    row = await svc.confirm_link_code(
        session,
        user,
        request.app.state.redis,
        body.code,
        body.chat_id,
    )
    await audit_svc.record(
        session,
        user,
        "telegram.confirm",
        target_type="telegram",
        target_id=row.chat_id,
        request=request,
    )
    await session.commit()
    return _link_out(row)


@router.delete("/link", response_model=LinkOut)
async def unlink_telegram(
    request: Request, user: CurrentUser, session: DbSession
) -> LinkOut:
    await svc.unlink(session, user.id)
    await audit_svc.record(
        session,
        user,
        "telegram.unlink",
        target_type="telegram",
        target_id=user.id,
        request=request,
    )
    await session.commit()
    return _link_out(None)


# --- S-68: публичный webhook обновлений ---


class WebhookOut(CamelModel):
    ok: bool


@router.post("/webhook", response_model=WebhookOut)
async def telegram_webhook(request: Request) -> WebhookOut:
    """Update от Telegram (S-68): secret-заголовок → /start|/stop.

    Метод публичный; аутентификация — сравнение
    `X-Telegram-Bot-Api-Secret-Token` (Telegram присылает его сам при
    setWebHook). Пустой секрет в конфигурации → 404.
    """
    from core.config import settings

    if not settings.telegram_webhook_secret:
        raise AppError("telegram_webhook_disabled", "Webhook не настроен", 404)
    provided: str | None = request.headers.get(svc.WEBHOOK_HEADER)
    if provided != settings.telegram_webhook_secret:
        raise AppError("telegram_webhook_secret", "Неверный secret", 403)
    try:
        update = await request.json()
    except Exception as exc:  # noqa: BLE001 — некорректный JSON
        raise AppError("telegram_webhook_badjson", "Некорректный JSON", 400) from exc
    if not isinstance(update, dict):
        return WebhookOut(ok=True)
    from core.db import session_factory

    async with session_factory() as session:
        reply = await svc.handle_update(session, request.app.state.redis, update)
        await session.commit()
        if reply is not None:
            message = update.get("message") or {}
            chat_id = str((message.get("chat") or {}).get("id") or "")
            if chat_id:
                await svc._reply(chat_id, reply)
    return WebhookOut(ok=True)
