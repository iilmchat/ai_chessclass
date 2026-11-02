"""S-50: Telegram — consent/link, code, outbox/retry, unsubscribe."""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from core.db import session_factory
from domains.telegram.models import TelegramLink, TelegramOutbox
from domains.telegram.service import deliver_pending, enqueue
from tests.conftest import API, login, register_verified


async def _link_client(make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}
    return client, headers, user_id


async def test_telegram_link_code_and_outbox(make_client, unique_email):
    client, headers, user_id = await _link_client(make_client, unique_email)

    response = await client.get(f"{API}/telegram/status", headers=headers)
    assert response.status_code == 200
    assert response.json()["linked"] is False

    # код привязки → confirm
    response = await client.post(f"{API}/telegram/link-code", headers=headers)
    assert response.status_code == 200, response.text
    code = response.json()["code"]
    response = await client.post(
        f"{API}/telegram/confirm",
        headers=headers,
        json={"code": code, "chatId": "123456789"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["linked"] is True

    async with session_factory() as session:
        assert await enqueue(session, user_id, "achievement", "Бейдж: Первый ход")
        await session.commit()

    calls: list[tuple[str, str]] = []

    async def sender(chat_id: str, text: str) -> int:
        calls.append((chat_id, text))
        return 200

    async with session_factory() as session:
        result = await deliver_pending(session, sender=sender)
        await session.commit()
        assert result["sent"] == 1
        row = (
            await session.execute(
                sa.select(TelegramOutbox).where(TelegramOutbox.user_id == user_id)
            )
        ).scalar_one()
        assert row.status == "sent"
        assert calls == [("123456789", "Бейдж: Первый ход")]

    # отписка: ссылка удалена, новые уведомления не ставятся
    response = await client.delete(f"{API}/telegram/link", headers=headers)
    assert response.status_code == 200
    assert response.json()["linked"] is False
    async with session_factory() as session:
        assert not await enqueue(session, user_id, "streak", "Стрик")
        assert (
            await session.execute(
                sa.select(TelegramLink).where(TelegramLink.user_id == user_id)
            )
        ).scalar_one_or_none() is None


async def test_telegram_consent_required_and_retry(make_client, unique_email):
    client, headers, user_id = await _link_client(make_client, unique_email)

    response = await client.post(
        f"{API}/telegram/link",
        headers=headers,
        json={"chatId": "987654321", "consent": False},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "telegram_consent_required"

    response = await client.post(
        f"{API}/telegram/link",
        headers=headers,
        json={"chatId": "987654321", "consent": True},
    )
    assert response.status_code == 200

    async with session_factory() as session:
        await enqueue(session, user_id, "report", "PDF готов")
        await session.commit()

    async def fail(_chat: str, _text: str) -> int:
        return 500

    async with session_factory() as session:
        result = await deliver_pending(session, sender=fail)
        await session.commit()
        assert result["failed"] == 1
        row = (
            await session.execute(
                sa.select(TelegramOutbox).where(TelegramOutbox.user_id == user_id)
            )
        ).scalar_one()
        assert row.attempts == 1 and row.status == "failed"
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async def ok(_chat: str, _text: str) -> int:
        return 204

    async with session_factory() as session:
        result = await deliver_pending(session, sender=ok)
        await session.commit()
        assert result["sent"] == 1


async def test_telegram_graceful_without_token(make_client, unique_email, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "")
    client, headers, _user_id = await _link_client(make_client, unique_email)
    response = await client.get(f"{API}/telegram/status", headers=headers)
    assert response.status_code == 200
    assert response.json()["configured"] is False

    async with session_factory() as session:
        result = await deliver_pending(session)
        assert result == {"sent": 0, "failed": 0, "disabled": 1}

