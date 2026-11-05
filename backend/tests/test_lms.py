"""S-49: LMS LRS — идемпотентная очередь, retry, статус/CSV."""

from datetime import UTC, datetime, timedelta

import httpx
import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from domains.lms import service as lms_svc
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


async def test_lrs_oauth_refresh_on_401(redis_client, monkeypatch):
    """S-79: MockTransport OAuth2 + 401 → refresh токена и повтор xAPI."""
    monkeypatch.setattr(settings, "lrs_enabled", True)
    monkeypatch.setattr(settings, "lrs_endpoint", "https://lrs.test")
    monkeypatch.setattr(
        settings, "lrs_oauth_token_url", "https://idp.test/oauth/token"
    )
    monkeypatch.setattr(settings, "lrs_oauth_client_id", "client")
    monkeypatch.setattr(settings, "lrs_oauth_client_secret", "secret")
    await redis_client.delete(lms_svc.OAUTH_CACHE_KEY)
    lms_svc._oauth_token.value = ""
    lms_svc._oauth_token.expires_at = 0.0

    token_calls = 0
    put_auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path.endswith("/oauth/token"):
            token_calls += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"token-{token_calls}",
                    "expires_in": 3600,
                },
                request=request,
            )
        put_auth.append(request.headers.get("authorization", ""))
        if len(put_auth) == 1:
            return httpx.Response(401, request=request)
        return httpx.Response(204, request=request)

    def fake_client(base_url: str, *args, **kwargs) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(lms_svc, "_http_client", fake_client)
    status_code = await lms_svc._send(
        {"id": "statement-1"}, redis=redis_client
    )
    assert status_code == 204
    assert token_calls == 2
    assert put_auth == ["Bearer token-1", "Bearer token-2"]
    assert await redis_client.get(lms_svc.OAUTH_CACHE_KEY) == "token-2"

    await redis_client.delete(lms_svc.OAUTH_CACHE_KEY)
    lms_svc._oauth_token.value = ""
    lms_svc._oauth_token.expires_at = 0.0


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
