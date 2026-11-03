"""S-65: workflow жалоб PvP — создание участником, ревью teacher/admin,
RBAC (student 403), статус-машина (open → reviewed/rejected), note факты."""


from domains.auth.models import UserRole
from tests.conftest import API, login, make_direct_user, register_verified

RANDOM_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)


async def _student_with_room(make_client, email):
    """Регистрация + бот + комната: (client, headers, user_id, room_id)."""
    client = await make_client()
    await register_verified(client, email)
    _c, access, user_id = await login(client, email)
    headers = {"Authorization": f"Bearer {access}"}
    response = await client.post(
        f"{API}/bots",
        json={"code": RANDOM_BOT, "entry": "choose_move"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    bot_id = int(response.json()["id"])
    response = await client.post(
        f"{API}/pvp/rooms",
        headers=headers,
        json={"botVersionId": bot_id},
    )
    assert response.status_code == 201, response.text
    room = response.json()
    return client, headers, user_id, int(room["id"])


async def _create_complaint(client, headers, room_id: int) -> int:
    response = await client.post(
        f"{API}/pvp/rooms/{room_id}/complaints",
        json={"reason": "соперник делает невозможные ходы"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "open"
    return int(response.json()["id"])


async def test_complaint_review_flow(admin_client, make_client, unique_email):
    client, headers, _uid, room_id = await _student_with_room(
        make_client, unique_email
    )
    complaint_id = await _create_complaint(client, headers, room_id)

    # student не может закрывать жалобы
    review_body = {"status": "reviewed", "note": "проверено учителем"}
    response = await client.patch(
        f"{API}/admin/pvp/complaints/{complaint_id}",
        json=review_body,
        headers=headers,
    )
    assert response.status_code == 403

    # admin закрывает: reviewed + note + reviewer
    response = await admin_client.patch(
        f"{API}/admin/pvp/complaints/{complaint_id}", json=review_body
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "reviewed"
    assert body["note"] == "проверено учителем"
    assert body["reviewedBy"] is not None

    # очередь со списком
    response = await admin_client.get(f"{API}/admin/pvp/complaints")
    assert response.status_code == 200
    target = next(
        r for r in response.json() if int(r["id"]) == complaint_id
    )
    assert target["status"] == "reviewed"

    # повторное ревью — 409 (статус-машина)
    response = await admin_client.patch(
        f"{API}/admin/pvp/complaints/{complaint_id}", json=review_body
    )
    assert response.status_code == 409


async def test_rejected_flow_and_bad_status(admin_client, make_client, unique_email):
    client, headers, _uid, room_id = await _student_with_room(
        make_client, f"a-{unique_email}"
    )
    complaint_id = await _create_complaint(client, headers, room_id)

    # неизвестный статус → 422
    response = await admin_client.patch(
        f"{API}/admin/pvp/complaints/{complaint_id}",
        json={"status": "closed"},
    )
    assert response.status_code == 422

    # rejected — допустимый переход
    response = await admin_client.patch(
        f"{API}/admin/pvp/complaints/{complaint_id}",
        json={"status": "rejected", "note": "нет оснований"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    # жалоба не существует → 404
    response = await admin_client.patch(
        f"{API}/admin/pvp/complaints/999999",
        json={"status": "rejected"},
    )
    assert response.status_code == 404


async def test_teacher_can_review(make_client, unique_email):
    client, headers, _uid, room_id = await _student_with_room(
        make_client, f"t-{unique_email}"
    )
    complaint_id = await _create_complaint(client, headers, room_id)

    teacher_email = f"cd-{unique_email}"
    await make_direct_user(teacher_email, role=UserRole.TEACHER)
    _c, teacher_access, _tuid = await login(client, teacher_email)

    response = await client.patch(
        f"{API}/admin/pvp/complaints/{complaint_id}",
        json={"status": "reviewed", "note": "проверено"},
        headers={"Authorization": f"Bearer {teacher_access}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reviewed"
