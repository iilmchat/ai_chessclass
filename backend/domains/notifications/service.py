"""S-83: очередь email (`email_outbox`) с retry/backoff.

Контракт:
- `enqueue` пишет pending-строку и делает flush (тот же transaction, что и
  бизнес-операция — письмо не потеряется при откате);
- `deliver_one` делает одну попытку доставки: успех → `sent`; исключение
  транспорта не пробрасывается — строка уходит в retry с `next_attempt_at`;
- `deliver_pending` — cron-проход по due-строкам (pending/failed);
- после `EMAIL_OUTBOX_MAX_ATTEMPTS` строка «паркуется» (next_attempt_at =
  +1 год) и больше не выбирается: разбор — вручную/через DLQ-подобный аудит.

В dev (`SMTP_HOST` пуст) `core.email.send_email` пишет письмо в лог и
возвращает False — доставка считается выполненной (`sent`), а
`deliver_pending` сообщает `disabled=1`, чтобы не выдавать консоль за SMTP.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.email import send_email
from domains.notifications.models import EmailOutbox

logger = logging.getLogger(__name__)

#: sender(to, subject, body) -> True при реальной SMTP-доставке, False — no-op
#: (dev-консоль). Ошибка доставки поднимается исключением.
SenderFn = Callable[[str, str, str], Awaitable[bool]]

#: допустимые статусы строки (совпадает с CheckConstraint в миграции 0035)
STATUSES = ("pending", "sent", "failed")
RETRYABLE_STATUSES = ("pending", "failed")
#: «Парковка» исчерпавшей попытки строки: очень далёкое будущее.
PARKED_DELAY = timedelta(days=365)


def _now() -> datetime:
    return datetime.now(UTC)


def retry_delay_seconds(attempts: int) -> int:
    """Экспоненциальная пауза перед повтором: 2, 4, … до 3600 секунд."""
    return min(3600, 2 ** min(attempts, 10))


def is_disabled_transport() -> bool:
    """True — SMTP не настроен (dev/CI), письма пишутся в лог."""
    return not settings.smtp_host


async def enqueue(
    session: AsyncSession,
    *,
    to: str,
    subject: str,
    body: str,
    kind: str,
) -> EmailOutbox:
    """Поставить письмо в очередь (pending, доставка — сразу или cron'ом)."""
    row = EmailOutbox(
        kind=kind,
        recipient=to.strip().lower(),
        subject=subject,
        body=body,
        status="pending",
        attempts=0,
        next_attempt_at=_now(),
    )
    session.add(row)
    await session.flush()
    return row


async def deliver_one(
    session: AsyncSession,
    row: EmailOutbox,
    *,
    sender: SenderFn | None = None,
) -> bool:
    """Одна попытка доставки строки; True — реальная SMTP-доставка.

    Исключение транспорта не пробрасывается: строка становится `failed` и
    повторяется позже (backoff). False при dev-консоли — это не ошибка:
    письмо записано в лог, строка помечается `sent`.
    """
    send = sender or send_email
    now = _now()
    row.attempts += 1
    try:
        delivered = await send(row.recipient, row.subject, row.body)
    except Exception as exc:  # noqa: BLE001 — любая ошибка = retry
        row.status = "failed"
        row.last_error = (str(exc)[:1000] or exc.__class__.__name__)
        if row.attempts >= settings.email_outbox_max_attempts:
            row.next_attempt_at = now + PARKED_DELAY
            logger.warning(
                "email_outbox: %s parked after %s attempts: %s",
                row.id,
                row.attempts,
                exc,
            )
        else:
            row.next_attempt_at = now + timedelta(
                seconds=retry_delay_seconds(row.attempts)
            )
            logger.warning(
                "email_outbox: %s attempt %s failed: %s",
                row.id,
                row.attempts,
                exc,
            )
        await session.flush()
        return False
    row.status = "sent"
    row.sent_at = now
    row.last_error = None
    await session.flush()
    return delivered


async def _due_rows(
    session: AsyncSession, *, limit: int | None
) -> list[EmailOutbox]:
    """Выбрать due-строки, заблокировав их для других воркеров.

    S-86: `FOR UPDATE SKIP LOCKED` — параллельные cron-тики (несколько
    arq-воркеров/реплик) не возьмут одну и ту же строку: занятые строки
    пропускаются, а не ждут освобождения. Блокировка живёт до commit/rollback
    транзакции `deliver_pending`, поэтому каждое письмо обрабатывается ровно
    одним процессом.
    """
    now = _now()
    return list(
        (
            await session.execute(
                select(EmailOutbox)
                .where(
                    EmailOutbox.status.in_(RETRYABLE_STATUSES),
                    EmailOutbox.next_attempt_at <= now,
                    EmailOutbox.attempts < settings.email_outbox_max_attempts,
                )
                .order_by(EmailOutbox.id)
                .limit(limit or settings.email_outbox_batch)
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )


async def deliver_pending(
    session: AsyncSession,
    *,
    sender: SenderFn | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Доставить все due-письма; агрегат для cron/логов."""
    rows = await _due_rows(session, limit=limit)
    sent = failed = 0
    for row in rows:
        delivered = await deliver_one(session, row, sender=sender)
        if delivered or row.status == "sent":
            # delivered=True — SMTP; status=sent при delivered=False — dev-консоль.
            sent += 1
        else:
            failed += 1
    await session.flush()
    disabled = int(sender is None and is_disabled_transport())
    return {"sent": sent, "failed": failed, "disabled": disabled}
