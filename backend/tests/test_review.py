"""S-52: SM-2 карточки, очередь, ответы и интеграции с ошибками."""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from core.db import session_factory
from domains.review import service as review_svc
from domains.review.models import ReviewCard, ReviewEvent
from tests.conftest import API, login, register_verified


async def _student(make_client, email):
    client = await make_client()
    await register_verified(client, email)
    _c, access, user_id = await login(client, email)
    return client, {"Authorization": f"Bearer {access}"}, user_id


async def test_review_queue_and_sm2(make_client, unique_email):
    client, headers, user_id = await _student(make_client, unique_email)
    response = await client.post(
        f"{API}/review/cards",
        headers=headers,
        json={"front": "Что такое list comprehension?", "back": "Выражение списка"},
    )
    assert response.status_code == 201, response.text
    card_id = int(response.json()["id"])

    response = await client.get(f"{API}/review/queue", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["dueCount"] == 1
    assert body["cards"][0]["front"] == "Что такое list comprehension?"

    response = await client.post(
        f"{API}/review/cards/{card_id}/answer",
        headers=headers,
        json={"rating": "good"},
    )
    assert response.status_code == 200, response.text
    card = response.json()
    assert card["intervalDays"] == 1
    assert card["repetitions"] == 1
    assert datetime.fromisoformat(card["dueAt"].replace("Z", "+00:00")) > datetime.now(UTC)

    # неверный ответ сбрасывает интервал и увеличивает lapses
    async with session_factory() as session:
        row = await session.get(ReviewCard, card_id)
        assert row is not None
        row.due_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    response = await client.post(
        f"{API}/review/cards/{card_id}/answer",
        headers=headers,
        json={"rating": "again"},
    )
    assert response.status_code == 200
    card = response.json()
    assert card["intervalDays"] == 1
    assert card["repetitions"] == 0
    assert card["lapses"] == 1

    async with session_factory() as session:
        assert (
            await session.execute(
                sa.select(ReviewEvent).where(ReviewEvent.user_id == user_id)
            )
        ).scalars().all()
    response = await client.get(f"{API}/review/stats", headers=headers)
    assert response.status_code == 200
    assert response.json()["reviewsToday"] == 2


async def test_review_daily_cap_and_source_dedup(make_client, unique_email):
    _client, _headers, user_id = await _student(make_client, unique_email)
    async with session_factory() as session:
        first = await review_svc.create_from_python(
            session,
            user_id,
            assignment_id=42,
            assignment_title="Циклы",
            topic="loops",
            failed_test=2,
        )
        again = await review_svc.create_from_python(
            session,
            user_id,
            assignment_id=42,
            assignment_title="Циклы",
            topic="loops",
            failed_test=2,
        )
        assert first.id == again.id
        chess = await review_svc.create_from_chess(
            session,
            user_id,
            game_id=7,
            ply=10,
            fen="8/8/8/8/8/8/8/K6k w - - 0 1",
            best_san="Ka2",
            played_san="Kb1",
        )
        assert chess.source_type == "chess"
        for index in range(25):
            await review_svc.create_card(
                session, user_id, front=f"card {index}", back="answer"
            )
        await session.commit()

    async with session_factory() as session:
        cards, due = await review_svc.queue(session, user_id)
        assert due >= 27
        assert len(cards) == 20  # дневной лимит
        assert all(card.user_id == user_id for card in cards)
