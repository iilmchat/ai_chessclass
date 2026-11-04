"""S-50: Telegram-привязка и outbox уведомлений.

S-68: webhook updates (/start — link_code, /stop — отписка), long-poll
fallback (getUpdates, offset в Redis, блокировка вора), teacher-события
(сдача/турнир/жалоба → уведомления учителям классов).
"""

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
#: S-68: ключи webhook/long-poll контура.
WEBHOOK_HEADER = "X-Telegram-Bot-Api-Secret-Token"
POLL_OFFSET_PREFIX = "telegram:lp:offset"
POLL_LOCK_KEY = "telegram:lp:lock"
POLL_LOCK_TTL_S = 90
#: Дневной лимит уведомлений на пользователя (S-50) — не трогаем.
DAILY_LIMIT = 20


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
        if used >= DAILY_LIMIT:
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


# --- S-68: webhook updates, long-poll fallback, teacher-события ---


def _http_client() -> httpx.AsyncClient:
    """httpx с egress-hook (S-61) — точка инъекции транспорта в тестах."""
    from core.egress import hostname_of, make_egress_hook

    return httpx.AsyncClient(
        timeout=15.0,
        event_hooks={
            "request": [
                make_egress_hook(hostname_of(settings.telegram_api_base) or "")
            ]
        },
    )


async def _tg_request(
    method: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
) -> httpx.Response:
    """Bot API запрос: POST method (+ тело/параметры)."""
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")
    url = (
        f"{settings.telegram_api_base.rstrip('/')}"
        f"/bot{settings.telegram_bot_token}/{method}"
    )
    async with _http_client() as client:
        return await client.post(url, json=json_body, params=params)


async def _reply(chat_id: str, text: str) -> None:
    """Прямой ответ в чат (webhook/long-poll); ошибка логируется."""
    try:
        response = await _tg_request(
            "sendMessage",
            json_body={
                "chat_id": chat_id,
                "text": text[:4000],
                "disable_web_page_preview": True,
            },
        )
        if response.status_code >= 300:
            logger.warning(
                "telegram: reply к %s — HTTP %s", chat_id, response.status_code
            )
    except Exception as exc:  # noqa: BLE001 — webhook всё равно отвечает 200
        logger.warning("telegram: reply к %s не отправлен: %s", chat_id, exc)


START_REPLY = "Готово: ChessClass уведомления привязаны к этому чату."
STOP_REPLY = "Отписано: привязка к ChessClass удалена."
HELP_REPLY = (
    "Этот бот принимает уведомления ChessClass.\n"
    "Привязка: /start <код> со ссылкой из профиля.\n"
    "Отписка: /stop."
)


async def handle_update(
    session: AsyncSession, redis, update: dict
) -> str | None:
    """Обработать один Telegram Update (S-68). Возвращает reply-текст."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    text = message.get("text")
    if not isinstance(chat, dict) or not isinstance(text, str):
        return None
    chat_id = str(chat.get("id") or "").strip()
    if not chat_id.isdigit() or not 5 <= len(chat_id) <= 32:
        return None

    parts = text.strip().split(maxsplit=1)
    command = parts[0].lower().split("@", 1)[0]
    argument = parts[1].strip() if len(parts) > 1 else ""

    if command in ("/start", "/link"):
        if not argument:
            return HELP_REPLY
        expected = await redis.get(f"{LINK_PREFIX}{argument}")
        if expected is None:
            return (
                "Код привязки недействителен или истёк — "
                "получите новый в профиле ChessClass."
            )
        user = (
            await session.execute(
                select(User).where(User.id == int(expected))
            )
        ).scalar_one_or_none()
        if user is None:
            return HELP_REPLY
        await redis.delete(f"{LINK_PREFIX}{argument}")
        await link(session, user, chat_id, True)
        await session.flush()
        return START_REPLY

    if command in ("/stop", "/unsubscribe"):
        row = (
            await session.execute(
                select(TelegramLink).where(TelegramLink.chat_id == chat_id)
            )
        ).scalar_one_or_none()
        if row is not None:
            await session.delete(row)
            await session.flush()
        return STOP_REPLY

    return HELP_REPLY


async def poll_updates_once(
    session: AsyncSession, redis
) -> dict[str, int]:
    """Один цикл long-poll getUpdates (S-68 fallback).

    Включается только через TELEGRAM_POLL_ENABLED; Redis-лок — защита от
    нескольких воркеров, offset хранится в Redis. Обработанные update'ы
    подтверждаются offset'ом после reply.
    """
    if not settings.telegram_poll_enabled or not settings.telegram_bot_token:
        return {"offset": int(await redis.get(POLL_OFFSET_PREFIX) or 0) or 0,
                "processed": 0, "disabled": 1}
    got_lock = await redis.set(
        POLL_LOCK_KEY, "1", ex=POLL_LOCK_TTL_S, nx=True
    )
    if not got_lock:
        return {"offset": int(await redis.get(POLL_OFFSET_PREFIX) or 0) or 0,
                "processed": 0, "locked": 1}
    saved = int(await redis.get(POLL_OFFSET_PREFIX) or 0) or 0
    response = await _tg_request(
        "getUpdates",
        params={
            "timeout": 0,
            "limit": min(settings.telegram_poll_limit, 50),
            "offset": saved + 1,
        },
    )
    if response.status_code >= 300:
        logger.warning("telegram: getUpdates — HTTP %s", response.status_code)
        return {"offset": saved, "processed": 0}
    try:
        updates = response.json() or []
    except ValueError:  # пустое/битое тело — как пустой список
        updates = []
    if not isinstance(updates, list):
        updates = []
    last_id = saved
    processed = 0
    for update in updates:
        update_id = update.get("update_id")
        if not isinstance(update_id, int) or update_id <= last_id:
            continue
        try:
            reply = await handle_update(session, redis, update)
            if reply is not None:
                chat = ((update.get("message") or {}).get("chat") or {})
                chat_id = str(chat.get("id") or "")
                if chat_id:
                    await _reply(chat_id, reply)
        except Exception as exc:  # noqa: BLE001 — не терять offset
            logger.warning("telegram: update %s failed: %s", update_id, exc)
        last_id = update_id
        processed += 1
    if last_id != saved:
        await redis.set(POLL_OFFSET_PREFIX, str(last_id))
    return {"offset": last_id, "processed": processed}


async def enqueue_teacher_events(
    session: AsyncSession,
    *,
    child_user_id: int,
    kind: str,
    text: str,
    redis=None,
) -> int:
    """Уведомить учителей классов, где состоит ученик (S-68).

    Возвращает число созданных outbox-строк (учитель без привязки —
    пропускается enqueue-лимитом S-50). Однократная защита от дублей
    вряд ли нужна: kind+текст уникальны по контексту события.
    """
    from domains.classes.models import ClassMember, Classroom

    teacher_ids = list(
        (
            await session.execute(
                select(Classroom.teacher_id)
                .join(ClassMember, ClassMember.class_id == Classroom.id)
                .where(ClassMember.user_id == child_user_id)
                .distinct()
            )
        ).scalars()
    )
    child = (
        await session.execute(select(User).where(User.id == child_user_id))
    ).scalar_one_or_none()
    label = (
        child.email if child is not None else str(child_user_id)
    )
    enqueued = 0
    for teacher_id in teacher_ids:
        link_row = await get_link(session, teacher_id)
        if link_row is None or not link_row.consent:
            continue
        if await enqueue(
            session, teacher_id, kind, f"{text} (ученик: {label})", redis=redis
        ):
            enqueued += 1
    return enqueued
