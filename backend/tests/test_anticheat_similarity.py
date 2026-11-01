"""S-24: plagiarism_suspected (exact-copy + similarity), profile_mismatch,
карточка ученика (кабинет учителя)."""


import sqlalchemy as sa

from core.db import session_factory
from domains.anticheat.models import AnticheatFlag
from domains.python_teacher.models import PyReferenceSolution
from tests.conftest import API, login, register_verified

GREET_TESTS = ['assert greet("Аня") == "Привет, Аня!"']


async def _setup_assignment_with_reference(admin_client) -> int:
    response = await admin_client.post(
        f"{API}/py/assignments",
        json={
            "slug": "test-plagiarism",
            "title": "Плагиат-тест",
            "level": "novice",
            "topic": "conditions",
            "statement": "Напиши функцию greet(name), возвращающую приветствие.",
            "tests": GREET_TESTS,
        },
    )
    assert response.status_code == 201
    assignment_id = int(response.json()["id"])
    async with session_factory() as session:
        session.add(
            PyReferenceSolution(
                assignment_id=assignment_id,
                source='def greet(name):\n    return f"Привет, {name}!"\n',
            )
        )
        await session.commit()
    return assignment_id


async def test_exact_copy_of_reference_flagged(
    admin_client, make_client, unique_email, worker_role
):
    assignment_id = await _setup_assignment_with_reference(admin_client)
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)

    # сдача — точная копия эталона
    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": 'def greet(name):\n    return f"Привет, {name}!"\n'},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    submission_id = int(response.json()["id"])

    async with session_factory() as session:
        flag = (
            await session.execute(
                sa.select(AnticheatFlag).where(
                    AnticheatFlag.user_id == user_id,
                    AnticheatFlag.kind == "plagiarism_suspected",
                )
            )
        ).scalar_one()
        assert float(flag.confidence) >= 0.95
        matches = flag.evidence["matches"]
        assert any(m["ref"] == "reference" for m in matches)
        _ = submission_id


async def test_original_solution_not_flagged(
    admin_client, make_client, unique_email, worker_role
):
    assignment_id = await _setup_assignment_with_reference(admin_client)
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)

    # оригинальное решение — другой текст (не сходится с эталоном)
    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": 'def greet(name):\n    return "Привет, " + name + "!"\n'},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200

    async with session_factory() as session:
        flag = (
            await session.execute(
                sa.select(AnticheatFlag).where(
                    AnticheatFlag.user_id == user_id,
                    AnticheatFlag.kind == "plagiarism_suspected",
                )
            )
        ).scalar_one_or_none()
        assert flag is None  # false-positive ≈ 0 на оригинальных решениях


async def test_teacher_student_card(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, student_id = await login(client, unique_email)

    response = await admin_client.get(
        f"{API}/admin/anticheat/students/{student_id}/card"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["userId"] == str(student_id)
    assert body["email"] == unique_email
    assert isinstance(body["flags"], list)
    assert isinstance(body["judgeSessions"], list)

    # чужой student → 404
    response = await admin_client.get(
        f"{API}/admin/anticheat/students/999999/card"
    )
    assert response.status_code == 404
