"""S-83: email outbox — очередь писем с retry/backoff.

Тесты идут в реальный dev-стек (RULES §6); строки помечаются kind
`test-email-outbox` и вычищаются фикстурой, чтобы не влиять на другие тесты.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from domains.notifications import service as svc
from domains.notifications.models import EmailOutbox

KIND = "test-email-outbox"
TO = "parent@example.com"


async def _failing_sender(to: str, subject: str, body: str) -> bool:
    raise OSError("smtp down")


@pytest.fixture(autouse=True)
async def _clean_outbox():
    async with session_factory() as session:
        await session.execute(
            sa.delete(EmailOutbox).where(EmailOutbox.kind == KIND)
        )
        await session.commit()
    yield


async def test_enqueue_creates_pending_row():
    async with session_factory() as session:
        row = await svc.enqueue(
            session,
            to=" Parent@Example.COM ",
            subject="Согласие",
            body="Текст",
            kind=KIND,
        )
        await session.commit()
        assert row.id
        assert row.recipient == TO
        assert row.status == "pending"
        assert row.attempts == 0
        assert row.sent_at is None
        assert row.next_attempt_at is not None


async def test_failure_then_retry_succeeds():
    calls = {"n": 0}

    async def flaky_sender(to: str, subject: str, body: str) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("smtp down")
        return True

    async with session_factory() as session:
        row = await svc.enqueue(
            session, to=TO, subject="Согласие", body="Текст", kind=KIND
        )
        await session.commit()

        delivered = await svc.deliver_one(session, row, sender=flaky_sender)
        await session.commit()
        assert delivered is False
        assert row.status == "failed"
        assert row.attempts == 1
        assert row.last_error is not None and "smtp down" in row.last_error
        assert row.next_attempt_at > datetime.now(UTC)

        # Эмулируем наступление времени повтора.
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

        result = await svc.deliver_pending(session, sender=flaky_sender)
        await session.commit()
        assert result["sent"] == 1
        assert result["failed"] == 0
        assert result["disabled"] == 0
        assert row.status == "sent"
        assert row.attempts == 2
        assert row.last_error is None
        assert row.sent_at is not None


async def test_dev_console_marks_sent_and_reports_disabled(monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", "")
    async with session_factory() as session:
        row = await svc.enqueue(
            session, to=TO, subject="Согласие", body="Ссылка", kind=KIND
        )
        await session.commit()

        result = await svc.deliver_pending(session)
        await session.commit()
        assert result == {"sent": 1, "failed": 0, "disabled": 1}
        assert row.status == "sent"
        assert row.attempts == 1
        assert row.last_error is None


async def test_parks_after_max_attempts(monkeypatch):
    monkeypatch.setattr(settings, "email_outbox_max_attempts", 2)
    async with session_factory() as session:
        row = await svc.enqueue(
            session, to=TO, subject="Согласие", body="Текст", kind=KIND
        )
        await session.commit()

        for attempt in range(2):
            await svc.deliver_pending(session, sender=_failing_sender)
            await session.commit()
            if attempt == 0:
                # backoff ещё не истёк — эмулируем следующий cron-тик.
                row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
                await session.commit()

        parked_until = row.next_attempt_at
        assert row.status == "failed"
        assert row.attempts == 2
        assert parked_until > datetime.now(UTC) + timedelta(days=300)

        # Даже если время «пришло», исчерпавшая лимит строка не выбирается.
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        result = await svc.deliver_pending(session, sender=_failing_sender)
        await session.commit()
        assert result["sent"] == 0
        assert result["failed"] == 0
        assert row.attempts == 2


async def test_empty_queue_returns_aggregate():
    removed = sa.delete(EmailOutbox).where(EmailOutbox.kind == KIND)
    async with session_factory() as session:
        await session.execute(removed)
        await session.commit()

        result = await svc.deliver_pending(session, sender=_failing_sender)
        await session.commit()
    assert set(result) == {"sent", "failed", "disabled"}
    assert result["disabled"] == 0


async def test_deliver_pending_skips_locked():
    """S-86: два параллельных deliver_pending не берут одну строку дважды."""
    bodies: list[str] = []
    first_started = asyncio.Event()
    allow_finish = asyncio.Event()

    async def blocking_sender(to: str, subject: str, body: str) -> bool:
        bodies.append(body)
        first_started.set()
        await allow_finish.wait()
        return True

    async with session_factory() as session_a, session_factory() as session_b:
        for index in range(5):
            await svc.enqueue(
                session_a,
                to=TO,
                subject=f"Согласие {index}",
                body=f"mail-{index}",
                kind=KIND,
            )
        await session_a.commit()

        task_a = asyncio.create_task(
            svc.deliver_pending(session_a, sender=blocking_sender, limit=5)
        )
        await asyncio.wait_for(first_started.wait(), timeout=5)

        # A уже выбрал все 5 строк и держит FOR UPDATE-блокировки. B не должен
        # ждать освобождения: SKIP LOCKED возвращает пустой набор сразу.
        task_b = asyncio.create_task(
            svc.deliver_pending(session_b, sender=blocking_sender, limit=5)
        )
        result_b = await asyncio.wait_for(task_b, timeout=3)
        assert result_b["sent"] == 0
        assert result_b["failed"] == 0
        await session_b.rollback()

        allow_finish.set()
        result_a = await asyncio.wait_for(task_a, timeout=10)
        await session_a.commit()

    assert result_a["sent"] == 5
    assert sorted(bodies) == [f"mail-{index}" for index in range(5)]


async def test_email_outbox_due_index_exists():
    """S-86: индекс (status, next_attempt_at) нужен для SKIP LOCKED-выборки."""
    async with session_factory() as session:
        indexdef = (
            await session.execute(
                sa.text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_email_outbox_status_next'"
                )
            )
        ).scalar_one_or_none()
    assert indexdef is not None
    assert "status" in indexdef
    assert "next_attempt_at" in indexdef


def test_worker_registers_outbox_task_and_cron():
    from app.worker import WorkerSettings

    names = {fn.__name__ for fn in WorkerSettings.functions}
    assert "email_outbox_deliver" in names
    cron_names = {
        getattr(job.coroutine, "__name__", str(job.coroutine))
        for job in WorkerSettings.cron_jobs
    }
    assert "email_outbox_deliver" in cron_names
