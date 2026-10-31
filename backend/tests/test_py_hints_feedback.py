"""S-09: лестница подсказок (seeded → LLM), лок решения, LLM-комментарий
к сдаче, low_effort-флаг, события навыков (минус-веса)."""

import sqlalchemy as sa

from core.db import session_factory
from tests.conftest import API, login, register_verified

GREET_TESTS = ['assert greet("Аня") == "Привет, Аня!"']


async def _setup(admin_client, make_client, unique_email, slug: str = "test-hint"):
    assignment_id = await admin_client.post(
        f"{API}/py/assignments",
        json={
            "slug": slug,
            "title": "Лестница",
            "level": "novice",
            "topic": "loops_basic",
            "statement": "Напиши функцию greet(name), возвращающую приветствие.",
            "starterCode": "def greet(name):\n    pass\n",
            "tests": GREET_TESTS,
        },
    )
    assert assignment_id.status_code == 201
    aid = int(assignment_id.json()["id"])

    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)
    return aid, client, access, user_id


def _h(access: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access}"}


async def test_hint_ladder_seeded_then_llm(
    admin_client, make_client, unique_email, redis_client
):
    aid, client, access, user_id = await _setup(
        admin_client, make_client, unique_email
    )
    headers = _h(access)

    # ступень 0 (нет сеед-подсказок → сразу LLM; в контейнере — echo)
    response = await client.post(
        f"{API}/py/assignments/{aid}/hint",
        json={"hintIdx": 0},
        headers=headers,
    )
    assert response.status_code == 200
    hint = response.json()
    assert hint["source"] == "llm"
    assert hint["content"]

    # событие навыка с минус-весом (-1.0 за LLM-подсказку)
    async with session_factory() as session:
        from domains.cognitive.models import SkillEvent

        row = (
            await session.execute(
                sa.select(SkillEvent).where(SkillEvent.user_id == user_id)
            )
        ).scalar_one()
        assert float(row.weight) == -1.0
        assert row.domain.value == "python"


async def test_solution_locked_until_three_failures(
    admin_client, make_client, unique_email
):
    aid, client, access, _user = await _setup(
        admin_client, make_client, unique_email, slug="test-solution"
    )
    # эталон решения (в тестовом задании заводим напрямую)
    from core.db import session_factory
    from domains.python_teacher.models import PyReferenceSolution

    async with session_factory() as session:
        solution = 'def greet(name):\n    return f"Привет, {name}!"\n'
        session.add(PyReferenceSolution(assignment_id=aid, source=solution))
        await session.commit()

    headers = _h(access)

    # две неудачные попытки → ещё locked
    for _ in range(2):
        response = await client.post(
            f"{API}/py/assignments/{aid}/submit",
            json={"code": "def greet(name):\n    return 1\n"},
            headers=headers,
        )
        assert response.json()["verdict"] == "failed"
    response = await client.get(f"{API}/py/assignments/{aid}/solution", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "solution_locked"

    # третья неудача → solution открывается
    await client.post(
        f"{API}/py/assignments/{aid}/submit",
        json={"code": "def greet(name):\n    return 1\n"},
        headers=headers,
    )
    response = await client.get(f"{API}/py/assignments/{aid}/solution", headers=headers)
    assert response.status_code == 200
    assert response.json()["source"]


async def test_submit_returns_llm_comment(admin_client, make_client, unique_email):
    aid, client, access, user_id = await _setup(
        admin_client, make_client, unique_email, slug="test-comment"
    )
    response = await client.post(
        f"{API}/py/assignments/{aid}/submit",
        json={"code": 'def greet(name):\n    return f"Привет, {name}!"\n'},
        headers=_h(access),
    )
    body = response.json()
    assert body["verdict"] == "passed"
    assert body["feedback"] is not None
    assert body["feedback"]["content"]
    assert body["feedback"]["modelUsed"]  # echo или облачная модель

    # py_feedback в БД + llm_calls журнал пополнился маршрутом comment
    async with session_factory() as session:
        from domains.python_teacher.models import PyFeedback

        row = (
            await session.execute(
                sa.select(PyFeedback).where(PyFeedback.user_id == user_id)
            )
        ).scalar_one()
        assert row.route == "python_teacher.comment"


async def test_low_effort_flag_on_tiny_code(admin_client, make_client, unique_email):
    aid, client, access, user_id = await _setup(
        admin_client, make_client, unique_email, slug="test-loweffort"
    )
    response = await client.post(
        f"{API}/py/assignments/{aid}/submit",
        json={"code": "x = 1\ny = 2\n"},  # 2 строки, решение неопределяющее
        headers=_h(access),
    )
    body = response.json()
    assert body["verdict"] in ("failed", "error")

    async with session_factory() as session:
        from domains.anticheat.models import AnticheatFlag

        flag = (
            await session.execute(
                sa.select(AnticheatFlag).where(
                    AnticheatFlag.user_id == user_id,
                    AnticheatFlag.kind == "low_effort",
                )
            )
        ).scalar_one()
        assert flag.status.value == "new"
        assert flag.domain.value == "python"
        evidence = flag.evidence
        assert "tiny_code" in evidence["reasons"]
        assert evidence["submissionId"] == int(body["id"])


async def test_low_effort_starter_copy_on_repeat(admin_client, make_client, unique_email):
    aid, client, access, user_id = await _setup(
        admin_client, make_client, unique_email, slug="test-copy"
    )
    starter = "def greet(name):\n    pass\n"
    for _ in range(2):  # повторные попытки с неизменённым starter'ом
        await client.post(
            f"{API}/py/assignments/{aid}/submit",
            json={"code": starter},
            headers=_h(access),
        )
    async with session_factory() as session:
        from domains.anticheat.models import AnticheatFlag

        flag = (
            await session.execute(
                sa.select(AnticheatFlag)
                .where(
                    AnticheatFlag.user_id == user_id,
                    AnticheatFlag.kind == "low_effort",
                )
                .order_by(AnticheatFlag.id.desc())
                .limit(1)
            )
        ).scalar_one()
        assert "starter_unchanged_repeat" in flag.evidence["reasons"]
        assert float(flag.confidence) >= 0.8


async def test_skill_event_on_submit(admin_client, make_client, unique_email):
    aid, client, access, user_id = await _setup(
        admin_client, make_client, unique_email, slug="test-event"
    )
    good = 'def greet(name):\n    return f"Привет, {name}!"\n'
    await client.post(
        f"{API}/py/assignments/{aid}/submit",
        json={"code": good},
        headers=_h(access),
    )
    async with session_factory() as session:
        from domains.cognitive.models import SkillEvent

        row = (
            await session.execute(
                sa.select(SkillEvent).where(SkillEvent.user_id == user_id)
            )
        ).scalar_one()
        assert float(row.weight) == 1.0  # passed → +1.0 (SPEC §8)
