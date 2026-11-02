"""S-49: LMS LRS — идемпотентная очередь, retry, статус/CSV."""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from core.db import session_factory
from domains.lms.models import LrsDelivery
from domains.lms.service import deliver_pending, enqueue_statements, status
from tests.conftest import API


async def _clear() -> None:
    async with session_factory() as session:
        await session.execute(sa.delete(LrsDelivery))
        await session.commit()


async def test_lrs_idempotency_and_retry(admin_client):
    _ = admin_client
    await _clear()
    async with session_factory() as session:
        queued = await enqueue_statements(session)
        assert queued > 0
        await session.commit()
        again = await enqueue_statements(session)
        assert again == 0
        await session.commit()

    calls: list[dict] = []

    async def ok_sender(payload: dict) -> int:
        calls.append(payload)
        return 204

    async with session_factory() as session:
        result = await deliver_pending(session, sender=ok_sender, limit=queued)
        await session.commit()
        assert result["sent"] == queued
        assert len(calls) == queued
        snap = await status(session)
        assert snap["counts"]["sent"] == queued

    # повторная доставка ничего не отправляет
    async with session_factory() as session:
        result = await deliver_pending(session, sender=ok_sender)
        await session.commit()
        assert result["sent"] == 0

    # failure → failed/attempts, затем retry
    async with session_factory() as session:
        await session.execute(sa.delete(LrsDelivery))
        await enqueue_statements(session)
        await session.commit()

    async def fail_sender(_payload: dict) -> int:
        return 500

    async with session_factory() as session:
        result = await deliver_pending(session, sender=fail_sender)
        await session.commit()
        assert result["failed"] > 0
        row = (
            await session.execute(select_one())
        ).scalar_one()
        assert row.status == "failed" and row.attempts == 1
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with session_factory() as session:
        result = await deliver_pending(session, sender=ok_sender)
        await session.commit()
        assert result["sent"] > 0
    await _clear()


async def test_lms_api_status_and_csv(admin_client):
    response = await admin_client.get(f"{API}/admin/lms/status")
    assert response.status_code == 200
    assert "counts" in response.json()
    response = await admin_client.get(f"{API}/admin/lms/deliveries")
    assert response.status_code == 200
    response = await admin_client.get(f"{API}/admin/lms/deliveries.csv")
    assert response.status_code == 200
    assert "statement_id" in response.text
    response = await admin_client.post(f"{API}/admin/lms/sync")
    assert response.status_code == 200, response.text
    assert "queued" in response.json()
    await _clear()


def select_one():
    return sa.select(LrsDelivery).limit(1)
