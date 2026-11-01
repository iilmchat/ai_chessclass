"""S-27 e2e-набор: сквозной сценарий §3.4 (регистрация → задание → инсайт →
бот-матч → дашборд → PDF). Полный Playwright — полировка; этот набор даёт
CI-стабильность контрактов через API с реальным SF/LLM-fallback.
"""

from uuid import uuid4

import sqlalchemy as sa

from core.db import session_factory
from tests.conftest import API, PASSWORD, login

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

RANDOM_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)


async def test_e2e_full_user_journey(
    admin_client, make_client, unique_email, worker_role, redis_client
):

    client = await make_client()

    # 1. регистрация + верификация
    response = await client.post(
        f"{API}/auth/register", json={"email": unique_email, "password": PASSWORD}
    )
    assert response.status_code == 201
    from domains.auth.models import EmailToken, User

    async with session_factory() as session:
        user_row = (
            await session.execute(sa.select(User).where(User.email == unique_email))
        ).scalar_one()
        token_row = (
            await session.execute(
                sa.select(EmailToken).where(
                    EmailToken.user_id == user_row.id,
                    EmailToken.kind == "verify",
                    EmailToken.used_at.is_(None),
                )
            )
        ).scalar_one()
        verify_token = token_row.token
    response = await client.post(f"{API}/auth/verify", json={"token": verify_token})
    assert response.status_code == 200

    # 2. задание (админ) → сдача → вердикт passed
    response = await admin_client.post(
        f"{API}/py/assignments",
        json={
            "slug": f"e2e-{uuid4().hex[:10]}",
            "title": "E2E задание",
            "level": "novice",
            "topic": "conditions",
            "statement": "Напиши функцию greet(name), возвращающую приветствие.",
            "tests": ['assert greet("Аня") == "Привет, Аня!"'],
        },
    )
    assert response.status_code == 201
    assignment_id = int(response.json()["id"])

    _c, access, user_id = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}
    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": 'def greet(name):\n    return f"Привет, {name}!"\n'},
        headers=headers,
    )
    assert response.json()["verdict"] == "passed"

    # 3. инсайт позиции (реальный SF в worker-роли)
    response = await client.post(
        f"{API}/chess/insight", json={"fen": START_FEN}, headers=headers
    )
    assert response.status_code == 200
    insight = response.json()
    assert insight["facts"] and insight["explanation"]

    # 4. бот-матч против random (полный луп)
    response = await client.post(
        f"{API}/bots", json={"code": RANDOM_BOT}, headers=headers
    )
    bot_id = int(response.json()["id"])

    from domains.bot_lab.match import run_match

    result = await run_match(bot_id, "random", redis_client)
    assert "error" not in result

    # 5. дашборд-данные: навыки 11, Elo-статистика
    response = await client.get(f"{API}/skills/me", headers=headers)
    assert len(response.json()["skills"]) == 11
    response = await client.get(f"{API}/bots/stats", headers=headers)
    stats = response.json()
    assert stats["wins"] + stats["losses"] + stats["draws"] == 1

    # 6. PDF родителям (админ) → файл скачан
    response = await admin_client.post(f"{API}/reports/pdf/{user_id}")
    assert response.status_code == 201
    report_id = int(response.json()["reportId"])
    response = await admin_client.get(f"{API}/reports/pdf/{report_id}")
    assert response.content.startswith(b"%PDF")

    # финал: у пользователя есть события навыков (сдача + матч)
    async with session_factory() as session:
        from domains.cognitive.models import SkillEvent

        events = (
            await session.execute(
                sa.select(SkillEvent).where(SkillEvent.user_id == user_id)
            )
        ).scalars().all()
        assert len(events) >= 1  # сдача порождает событие по теме задания
