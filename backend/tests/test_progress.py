"""S-42: стрики, бейджи, age_group и прогресс после сдачи."""

from datetime import date

import sqlalchemy as sa

from core.db import session_factory
from domains.auth.models import User, UserRole
from domains.progress.models import UserAchievement
from domains.progress.service import get_progress, record_passed_solution
from tests.conftest import API, login, make_direct_user, register_verified

GOOD_CODE = 'def greet(name):\n    return f"Привет, {name}!"\n'
GREET_TESTS = ['assert greet("Мир") == "Привет, Мир!"']


async def _student(client, email: str):
    await make_direct_user(email, UserRole.STUDENT)
    _client, access, user_id = await login(client, email)
    return {"Authorization": f"Bearer {access}"}, user_id


async def test_streak_growth_reset_and_one_time_badges(
    admin_client, unique_email
):
    _ = admin_client  # seeds: каталог achievements
    await make_direct_user(unique_email, UserRole.STUDENT)
    async with session_factory() as session:
        user = await session.get(User, int(
            (await session.execute(
                sa.select(User.id).where(User.email == unique_email)
            )).scalar_one()
        ))
        assert user is not None

        progress, awards = await record_passed_solution(
            session, user, "loops_basic", 1, today=date(2026, 1, 1)
        )
        assert progress.solved_count == 1
        assert progress.current_streak == 1
        assert {a.code for a in awards} == {"first_solution"}

        # повторное решение того же задания — без изменений/повторных бейджей
        progress, awards = await record_passed_solution(
            session, user, "loops_basic", 1, today=date(2026, 1, 1)
        )
        assert progress.solved_count == 1
        assert progress.current_streak == 1
        assert awards == []

        progress, _ = await record_passed_solution(
            session, user, "conditions", 2, today=date(2026, 1, 2)
        )
        assert progress.current_streak == 2
        progress, awards = await record_passed_solution(
            session, user, "functions", 3, today=date(2026, 1, 3)
        )
        assert progress.current_streak == 3
        assert progress.longest_streak == 3
        codes = {a.code for a in awards}
        assert "streak_3" in codes
        assert "topics_3" in codes

        # пропуск дня → текущий стрик 1, лучший сохраняется
        progress, _ = await record_passed_solution(
            session, user, "debugging", 4, today=date(2026, 1, 5)
        )
        assert progress.current_streak == 1
        assert progress.longest_streak == 3
        progress, _ = await record_passed_solution(
            session, user, "complexity", 5, today=date(2026, 1, 6)
        )
        assert progress.current_streak == 2

        await session.commit()
        awarded = (
            await session.execute(
                sa.select(UserAchievement).where(UserAchievement.user_id == user.id)
            )
        ).scalars().all()
        assert len(awarded) == len({a.achievement_id for a in awarded})
        assert len(awarded) >= 4

        snapshot = await get_progress(session, user.id)
        assert snapshot["solvedCount"] == 5
        assert snapshot["longestStreak"] == 3
        assert len(snapshot["achievements"]) == 6
        assert sum(1 for a in snapshot["achievements"] if a["awarded"]) >= 4


async def test_age_group_patch(make_client, unique_email):
    client = await make_client()
    headers, _uid = await _student(client, unique_email)
    response = await client.get(f"{API}/profile/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["ageGroup"] == "unknown"

    response = await client.patch(
        f"{API}/profile/me", json={"ageGroup": "teen"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["ageGroup"] == "teen"

    response = await client.patch(
        f"{API}/profile/me", json={"ageGroup": "too-old"}, headers=headers
    )
    assert response.status_code == 422


async def test_progress_after_passed_submission(
    admin_client, make_client, unique_email
):
    response = await admin_client.post(
        f"{API}/py/assignments",
        json={
            "slug": "test-progress",
            "title": "Прогресс",
            "level": "novice",
            "topic": "functions",
            "statement": "Напиши greet(name).",
            "starterCode": "def greet(name):\n    pass\n",
            "tests": GREET_TESTS,
        },
    )
    assert response.status_code == 201
    assignment_id = int(response.json()["id"])

    client = await make_client()
    await register_verified(client, unique_email)
    _client, access, user_id = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": GOOD_CODE},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["verdict"] == "passed"

    response = await client.get(f"{API}/progress/me", headers=headers)
    assert response.status_code == 200, response.text
    progress = response.json()
    assert progress["userId"] == str(user_id)
    assert progress["solvedCount"] == 1
    assert progress["currentStreak"] == 1
    assert progress["longestStreak"] == 1
    first = next(a for a in progress["achievements"] if a["code"] == "first_solution")
    assert first["awarded"] is True
