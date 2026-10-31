"""E2E python-домена (S-08): CRUD заданий, сдача, вердикты песочницы."""

import sqlalchemy as sa

from core.config import settings
from tests.conftest import API, login, register_verified

GREET_TESTS = [
    'assert greet("Аня") == "Привет, Аня!"',
    'assert greet("X") == "Привет, X!"',
]


async def _create_assignment(admin_client, slug: str = "test-greet", **overrides) -> int:
    payload = {
        "slug": slug,
        "title": "Тестовое задание",
        "level": "novice",
        "topic": "conditions",
        "statement": "Напиши функцию greet(name), возвращающую приветствие.",
        "starterCode": "def greet(name):\n    pass\n",
        "tests": GREET_TESTS,
        "hints": [{"idx": 0, "kind": "concept", "content": "f-строка"}],
        **overrides,
    }
    response = await admin_client.post(f"{API}/py/assignments", json=payload)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def test_admin_creates_student_lists(admin_client, make_client, unique_email):
    assignment_id = await _create_assignment(admin_client)
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)

    response = await client.get(
        f"{API}/py/assignments", headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 200
    page = response.json()
    assert page["total"] >= 1
    assert any(int(item["id"]) == assignment_id for item in page["items"])

    # student не может создавать
    response = await client.post(
        f"{API}/py/assignments",
        json={
            "slug": "test-x",
            "title": "X",
            "level": "novice",
            "topic": "conditions",
            "statement": "Какое-то длинное условие задания",
            "tests": ["assert True"],
        },
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 403


async def test_detail_hides_tests_from_student(admin_client, make_client, unique_email):
    assignment_id = await _create_assignment(admin_client, slug="test-detail")
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)

    response = await client.get(
        f"{API}/py/assignments/{assignment_id}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tests"] is None  # ученику тесты не отдаём
    assert body["testsCount"] == len(GREET_TESTS)
    assert body["statement"].startswith("Напиши")

    # admin видит тесты
    response = await admin_client.get(f"{API}/py/assignments/{assignment_id}")
    assert response.json()["tests"] is not None


async def test_submit_passed_verdict(admin_client, make_client, unique_email):
    assignment_id = await _create_assignment(admin_client, slug="test-passed")
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    good_code = 'def greet(name):\n    return f"Привет, {name}!"\n'
    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": good_code},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verdict"] == "passed"
    assert body["passedTests"] == 2 and body["totalTests"] == 2

    submission_id = int(body["id"])
    response = await client.get(
        f"{API}/py/submissions/{submission_id}", headers=headers
    )
    assert response.status_code == 200


async def test_submit_failed_with_failed_test(admin_client, make_client, unique_email):
    assignment_id = await _create_assignment(admin_client, slug="test-failed")
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)

    bad_code = 'def greet(name):\n    return f"Hi, {name}!"\nprint("мой вывод")\n'
    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": bad_code},
        headers={"Authorization": f"Bearer {access}"},
    )
    body = response.json()
    assert body["verdict"] == "failed"
    assert body["passedTests"] == 0
    assert body["failedTest"] is not None
    assert "мой вывод" in body["stdoutDigest"]


async def test_submit_restricted_import_os(admin_client, make_client, unique_email):
    assignment_id = await _create_assignment(admin_client, slug="test-restricted")
    client = await make_client()
    await register_verified(client, unique_email)
    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": "import os\nprint(os.listdir())"},
        headers={"Authorization": f"Bearer {(await login(client, unique_email))[1]}"},
    )
    assert response.json()["verdict"] == "restricted"


async def test_submit_timeout(monkeypatch, admin_client, make_client, unique_email):
    monkeypatch.setattr(settings, "sandbox_timeout_s", 1.5)  # не растягиваем прогон
    assignment_id = await _create_assignment(admin_client, slug="test-timeout")
    client = await make_client()
    await register_verified(client, unique_email)
    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": "while True:\n    pass\n"},
        headers={"Authorization": f"Bearer {(await login(client, unique_email))[1]}"},
    )
    assert response.json()["verdict"] == "timeout"


async def test_submit_error_runtime(admin_client, make_client, unique_email):
    assignment_id = await _create_assignment(admin_client, slug="test-error")
    client = await make_client()
    await register_verified(client, unique_email)
    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": "def greet(name):\n    return 1 / 0\n"},
        headers={"Authorization": f"Bearer {(await login(client, unique_email))[1]}"},
    )
    body = response.json()
    assert body["verdict"] == "error"


async def test_submission_privacy(admin_client, make_client, unique_email):
    assignment_id = await _create_assignment(admin_client, slug="test-privacy")
    client = await make_client()
    email_a = f"a-{unique_email}"
    email_b = f"b-{unique_email}"
    await register_verified(client, email_a)
    await register_verified(client, email_b)
    _c, access_a, _ = await login(client, email_a)
    _c, access_b, _ = await login(client, email_b)

    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": 'def greet(name):\n    return f"Привет, {name}!"\n'},
        headers={"Authorization": f"Bearer {access_a}"},
    )
    submission_id = int(response.json()["id"])

    # чужой студент → 403; админ → видит
    response = await client.get(
        f"{API}/py/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {access_b}"},
    )
    assert response.status_code == 403
    response = await admin_client.get(f"{API}/py/submissions/{submission_id}")
    assert response.status_code == 200


async def test_assignment_duplicate_slug_conflict(admin_client):
    await _create_assignment(admin_client, slug="test-dup")
    response = await admin_client.post(
        f"{API}/py/assignments",
        json={
            "slug": "test-dup",
            "title": "Дубль",
            "level": "novice",
            "topic": "conditions",
            "statement": "Какое-то длинное условие задания",
            "tests": ["assert True"],
        },
    )
    assert response.status_code == 409


async def test_invalid_tests_rejected(admin_client):
    response = await admin_client.post(
        f"{API}/py/assignments",
        json={
            "slug": "test-multiline",
            "title": "Многострочный тест",
            "level": "novice",
            "topic": "conditions",
            "statement": "Какое-то длинное условие задания",
            "tests": ["assert True\nassert 1 == 1"],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_tests"


async def test_seeded_tasks_present_and_idempotent():
    """Сиды заданий присутствуют и идемпотентны (повторный прогон)."""
    from core.db import session_factory
    from db.seeds_tasks import ASSIGNMENTS, seed_tasks
    from domains.python_teacher.models import PyAssignment

    async with session_factory() as session:
        await seed_tasks(session)
        await session.commit()
        count = (
            await session.execute(
                sa.select(sa.func.count()).select_from(PyAssignment)
            )
        ).scalar_one()
        assert count >= len(ASSIGNMENTS)
