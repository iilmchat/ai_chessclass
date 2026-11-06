"""S-83: email outbox — очередь писем с retry/backoff.

Тесты идут в реальный dev-стек (RULES §6); строки помечаются kind
`test-email-outbox` и вычищаются фикстурой, чтобы не влиять на другие тесты.
"""

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


def test_worker_registers_outbox_task_and_cron():
    from app.worker import WorkerSettings

    names = {fn.__name__ for fn in WorkerSettings.functions}
    assert "email_outbox_deliver" in names
    cron_names = {
        getattr(job.coroutine, "__name__", str(job.coroutine))
        for job in WorkerSettings.cron_jobs
    }
    assert "email_outbox_deliver" in cron_names
