"""S-68: Telegram webhook (secret, /start, /stop), long-poll fallback,
teacher-события (сдача) и алерт failed-outbox в /ops."""

import httpx
import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from domains.auth.models import User
from domains.classes.models import ClassMember, Classroom
from domains.lms.models import LrsDelivery
from domains.observability import service as obs_svc
from domains.telegram import service as svc
from domains.telegram.models import TelegramLink, TelegramOutbox
from tests.conftest import API, login, register_verified

REPLIES: list[str] = []


def _patch_replies(monkeypatch) -> None:
    """Инъекция транспорта: sendMessage собираем, прочие методы → []."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sendMessage"):
            REPLIES.append(request.content.decode())
            return httpx.Response(200)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)

    def fake_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=15.0)

    monkeypatch.setattr(svc, "_http_client", fake_client)


async def _client_with_account(make_client, unique_email) -> tuple:
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)
    return client, {"Authorization": f"Bearer {access}"}, user_id


async def test_webhook_requires_secret(make_client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret-tg-68")
    client = await make_client()
    update = {"update_id": 1, "message": {"text": "/start abc"}}
    response = await client.post(f"{API}/telegram/webhook", json=update)
    assert response.status_code == 403
    response = await client.post(
        f"{API}/telegram/webhook",
        json=update,
        headers={svc.WEBHOOK_HEADER: "wrong"},
    )
    assert response.status_code == 403


async def test_webhook_start_binds_account(make_client, unique_email, monkeypatch) -> None:
    _patch_replies(monkeypatch)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret-tg-68")
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    client, headers, user_id = await _client_with_account(make_client, unique_email)

    response = await client.post(f"{API}/telegram/link-code", headers=headers)
    assert response.status_code == 200
    code = response.json()["code"]

    update = {
        "update_id": 1,
        "message": {"text": f"/start {code}", "chat": {"id": "222333444"}},
    }
    response = await client.post(
        f"{API}/telegram/webhook",
        json=update,
        headers={svc.WEBHOOK_HEADER: "s3cret-tg-68"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True

    async with session_factory() as session:
        link_row = (
            await session.execute(
                sa.select(TelegramLink).where(TelegramLink.user_id == user_id)
            )
        ).scalar_one()
        assert link_row.chat_id == "222333444"
        assert link_row.consent is True
        await session.delete(link_row)
        await session.commit()
    assert REPLIES and "Готово" in "".join(REPLIES)


async def test_webhook_unknown_code_replies_help(make_client, monkeypatch) -> None:
    _patch_replies(monkeypatch)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret-tg-68")
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    client = await make_client()
    update = {
        "update_id": 2,
        "message": {"text": "/start deadbeef", "chat": {"id": "555000111"}},
    }
    response = await client.post(
        f"{API}/telegram/webhook",
        json=update,
        headers={svc.WEBHOOK_HEADER: "s3cret-tg-68"},
    )
    assert response.status_code == 200
    assert any("недействителен" in body for body in REPLIES)


async def test_webhook_stop_unlinks(make_client, unique_email, monkeypatch) -> None:
    _patch_replies(monkeypatch)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret-tg-68")
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    client, headers, user_id = await _client_with_account(make_client, unique_email)
    response = await client.post(
        f"{API}/telegram/link",
        headers=headers,
        json={"chatId": "741036985", "consent": True},
    )
    assert response.status_code == 200

    update = {
        "update_id": 7,
        "message": {"text": "/stop", "chat": {"id": "741036985"}},
    }
    response = await client.post(
        f"{API}/telegram/webhook",
        json=update,
        headers={svc.WEBHOOK_HEADER: "s3cret-tg-68"},
    )
    assert response.status_code == 200
    async with session_factory() as session:
        assert (
            await session.execute(
                sa.select(TelegramLink).where(TelegramLink.user_id == user_id)
            )
        ).scalar_one_or_none() is None


async def test_long_poll_disabled_and_offset(make_client, redis_client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "telegram_poll_enabled", False)
    async with session_factory() as session:
        result = await svc.poll_updates_once(session, redis_client)
    assert result["processed"] == 0
    assert result["disabled"] == 1


async def test_long_poll_no_updates_no_offset_change(
    make_client, redis_client, monkeypatch
) -> None:
    _patch_replies(monkeypatch)
    monkeypatch.setattr(settings, "telegram_poll_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    await redis_client.delete(svc.POLL_OFFSET_PREFIX)
    async with session_factory() as session:
        result = await svc.poll_updates_once(session, redis_client)
        await session.commit()
    # MockTransport отдаёт пустой список updates — offset не растёт
    assert result["processed"] == 0
    assert result["offset"] == 0


async def test_teacher_events_enqueued_and_failed_alert(
    make_client, unique_email, redis_client
) -> None:
    client, headers, user_id = await _client_with_account(
        make_client, unique_email
    )
    _ = client, headers
    async with session_factory() as session:
        teacher = (
            (
                await session.execute(
                    sa.select(User).where(User.email == "teacher@chessclass.dev")
                )
            )
            .scalars()
            .one()
        )
        session.add(
            TelegramLink(user_id=teacher.id, chat_id="900140070", consent=True)
        )
        student = (
            (
                await session.execute(
                    sa.select(User).where(User.email == unique_email)
                )
            )
            .scalars()
            .one()
        )
        classroom = Classroom(
            name="TG-68 класс",
            teacher_id=teacher.id,
            invite_code="tg68ab12cd",
        )
        session.add(classroom)
        await session.flush()
        session.add(ClassMember(class_id=classroom.id, user_id=student.id))
        await session.commit()
    try:
        async with session_factory() as session:
            student = (
                (
                    await session.execute(
                        sa.select(User).where(User.email == unique_email)
                    )
                )
                .scalars()
                .one()
            )
            count = await svc.enqueue_teacher_events(
                session,
                child_user_id=student.id,
                kind="teacher_submission",
                text="Задание #1 сдано",
                redis=redis_client,
            )
            await session.commit()
            assert count == 1
            rows = list(
                (
                    await session.execute(
                        sa.select(TelegramOutbox).where(
                            TelegramOutbox.kind == "teacher_submission"
                        )
                    )
                ).scalars()
            )
            assert len(rows) == 1 and rows[0].user_id != student.id
            assert "ученик" in rows[0].text
            # failed outbox → алерт на /ops
            rows[0].status = "failed"
            await session.commit()

        async with session_factory() as alert_session:
            alerts = await obs_svc.alerts(alert_session, redis_client)
        codes = {a["code"] for a in alerts}
        assert "telegram_outbox_failed" in codes
    finally:
        async with session_factory() as session:
            await session.execute(
                sa.delete(TelegramOutbox).where(
                    TelegramOutbox.kind == "teacher_submission"
                )
            )
            await session.execute(
                sa.delete(TelegramLink).where(TelegramLink.chat_id == "900140070")
            )
            await session.execute(
                sa.delete(Classroom).where(Classroom.name == "TG-68 класс")
            )
            await session.commit()


async def test_lrs_failed_alerts(make_client, redis_client) -> None:
    statement_id = "__incl-uuid-68__"
    async with session_factory() as session:
        session.add(
            LrsDelivery(statement_id=statement_id, payload={}, status="failed")
        )
        await session.commit()
        alerts = await obs_svc.alerts(session, redis_client)
        codes = {a["code"] for a in alerts}
        assert "lrs_deliveries_failed" in codes
        await session.execute(
            sa.delete(LrsDelivery).where(
                LrsDelivery.statement_id == statement_id
            )
        )
        await session.commit()
