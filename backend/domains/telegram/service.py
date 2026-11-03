"""S-50: Telegram-привязка и outbox уведомлений."""

import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from domains.auth.models import User
from domains.telegram.models import TelegramLink, TelegramOutbox

logger = logging.getLogger(__name__)

STATUSES = ("pending", "sent", "failed")
SenderFn = Callable[[str, str], Awaitable[int]]
LINK_PREFIX = "telegram:link:"
NOTIFY_PREFIX = "telegram:notify:"


async def get_link(session: AsyncSession, user_id: int) -> TelegramLink | None:
    return await session.get(TelegramLink, user_id)


async def link(
    session: AsyncSession, user: User, chat_id: str, consent: bool
) -> TelegramLink:
    clean = chat_id.strip()
    if not consent:
        raise AppError("telegram_consent_required", "Нужно согласие на уведомления", 422)
    if not clean.isdigit() or not 5 <= len(clean) <= 32:
        raise AppError("telegram_chat_invalid", "Некорректный chat_id", 422)
    existing = await session.get(TelegramLink, user.id)
    if existing is None:
        existing = TelegramLink(user_id=user.id, chat_id=clean, consent=True)
        session.add(existing)
    else:
        existing.chat_id = clean
        existing.consent = True
    await session.flush()
    return existing


async def unlink(session: AsyncSession, user_id: int) -> None:
    row = await session.get(TelegramLink, user_id)
    if row is not None:
        await session.delete(row)
        await session.flush()


async def make_link_code(redis, user_id: int) -> tuple[str, str]:
    code = secrets.token_urlsafe(8)
    if redis is not None:
        await redis.setex(
            f"{LINK_PREFIX}{code}", settings.telegram_link_ttl_s, str(user_id)
        )
    return code, f"https://t.me/chessclass_bot?start={code}"


async def confirm_link_code(
    session: AsyncSession, user: User, redis, code: str, chat_id: str
) -> TelegramLink:
    if redis is None:
        raise AppError("telegram_unavailable", "Redis недоступен", 503)
    expected = await redis.get(f"{LINK_PREFIX}{code}")
    if expected is None or str(expected) != str(user.id):
        raise AppError("telegram_code_invalid", "Код привязки недействителен", 422)
    await redis.delete(f"{LINK_PREFIX}{code}")
    return await link(session, user, chat_id, True)


async def enqueue(
    session: AsyncSession,
    user_id: int,
    kind: str,
    text: str,
    *,
    redis=None,
) -> bool:
    link_row = await get_link(session, user_id)
    if link_row is None or not link_row.consent:
        return False
    if redis is not None:
        key = f"{NOTIFY_PREFIX}{user_id}:{datetime.now(UTC).date().isoformat()}"
        used = int(await redis.get(key) or 0)
        if used >= 20:
            return False
        await redis.incr(key)
        await redis.expire(key, 2 * 24 * 3600)
    session.add(
        TelegramOutbox(
            user_id=user_id,
            kind=kind,
            text=text[:4000],
            status="pending",
            next_attempt_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return True


async def _send(chat_id: str, text: str) -> int:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")
    url = (
        f"{settings.telegram_api_base.rstrip('/')}"
        f"/bot{settings.telegram_bot_token}/sendMessage"
    )
    from core.egress import hostname_of, make_egress_hook

    async with httpx.AsyncClient(
        timeout=15.0,
        event_hooks={
            # S-61: egress allowlist (telegram_api_base разрешён как настроенный)
            "request": [
                make_egress_hook(hostname_of(settings.telegram_api_base) or "")
            ]
        },
    ) as client:
        response = await client.post(
            url,
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        )
    return response.status_code


async def deliver_pending(
    session: AsyncSession,
    *,
    sender: SenderFn | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    if sender is None and not settings.telegram_bot_token:
        return {"sent": 0, "failed": 0, "disabled": 1}
    fetch = sender or _send
    now = datetime.now(UTC)
    rows = list(
        (
            await session.execute(
                select(TelegramOutbox)
                .where(
                    TelegramOutbox.status.in_(("pending", "failed")),
                    TelegramOutbox.next_attempt_at <= now,
                )
                .order_by(TelegramOutbox.id)
                .limit(limit or settings.telegram_batch)
            )
        ).scalars()
    )
    sent = failed = 0
    for row in rows:
        link_row = await get_link(session, row.user_id)
        if link_row is None or not link_row.consent:
            row.status = "failed"
            row.last_error = "telegram link missing/consent revoked"
            failed += 1
            continue
        row.attempts += 1
        try:
            status = await fetch(link_row.chat_id, row.text)
            if 200 <= status < 300:
                row.status = "sent"
                row.sent_at = datetime.now(UTC)
                row.last_error = None
                sent += 1
            else:
                row.status = "failed"
                row.last_error = f"HTTP {status}"
                row.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(3600, 2 ** min(row.attempts, 10))
                )
                failed += 1
        except Exception as exc:  # noqa: BLE001 - retry позже
            row.status = "failed"
            row.last_error = str(exc)[:1000]
            row.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=min(3600, 2 ** min(row.attempts, 10))
            )
            failed += 1
            logger.warning("telegram: outbox %s failed: %s", row.id, exc)
    await session.flush()
    return {"sent": sent, "failed": failed, "disabled": 0}


async def status(session: AsyncSession, user: User) -> dict:
    link_row = await get_link(session, user.id)
    counts = {
        name: int(count)
        for name, count in (
            await session.execute(
                select(TelegramOutbox.status, func.count())
                .where(TelegramOutbox.user_id == user.id)
                .group_by(TelegramOutbox.status)
            )
        ).all()
    }
    return {
        "linked": link_row is not None,
        "consent": bool(link_row and link_row.consent),
        "configured": bool(settings.telegram_bot_token),
        "counts": {name: counts.get(name, 0) for name in STATUSES},
    }
