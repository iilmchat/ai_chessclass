"""S-23: judge-сессии — старт (echo), транскрипт, вердикт учителя."""


from core.db import session_factory
from domains.anticheat.models import JudgeSession
from tests.conftest import API, login, register_verified


async def test_judge_start_transcript_and_verdict(
    admin_client, make_client, unique_email
):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    # ученик запускает judge-сессию (echo в dev — но пайплайн полный)
    response = await client.post(
        f"{API}/admin/anticheat/judge",
        json={
            "sourceRef": "py_submission:1",
            "question": "Этот код проверяет, чётное ли число",
            "studentCode": "def f(n):\n    return n % 2 == 0\n",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["answer"]
    assert body["modelUsed"]

    session_id = int(body["id"])
    async with session_factory() as session:
        row = await session.get(JudgeSession, session_id)
        assert row is not None
        assert row.user_id == user_id
        assert row.transcript[0]["role"] == "system"  # транскрипт хранится

    # учитель видит сессию и выносит вердикт
    response = await admin_client.get(
        f"{API}/admin/anticheat/judge", params={"userId": user_id}
    )
    assert response.status_code == 200
    assert any(int(s["id"]) == session_id for s in response.json())

    response = await admin_client.post(
        f"{API}/admin/anticheat/judge/{session_id}/verdict",
        json={"verdict": "Понимание подтверждено — флаг снят"},
    )
    assert response.status_code == 200

    # student не может вердиктить
    response = await client.post(
        f"{API}/admin/anticheat/judge/{session_id}/verdict",
        json={"verdict": "сам себе вердикт"},
        headers=headers,
    )
    assert response.status_code == 403
