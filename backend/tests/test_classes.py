"""S-40: классы — создание, инвайты, участники, дашборд, RBAC."""

from domains.auth.models import UserRole
from tests.conftest import API, login, make_direct_user


async def _teacher(client, email: str):
    await make_direct_user(email, UserRole.TEACHER)
    _client, access, user_id = await login(client, email)
    return {"Authorization": f"Bearer {access}"}, user_id


async def _student(client, email: str):
    await make_direct_user(email, UserRole.STUDENT)
    _client, access, user_id = await login(client, email)
    return {"Authorization": f"Bearer {access}"}, user_id


async def test_class_create_join_and_dashboard(
    admin_client, make_client, unique_email
):
    _ = admin_client  # seeds: 11 навыков для дашборда
    client = await make_client()
    teacher_headers, teacher_id = await _teacher(client, f"t-{unique_email}")
    student_headers, student_id = await _student(client, unique_email)

    response = await client.post(
        f"{API}/classes", json={"name": "Шахматный 5А"}, headers=teacher_headers
    )
    assert response.status_code == 201, response.text
    created = response.json()
    class_id = int(created["id"])
    assert created["teacherId"] == str(teacher_id)
    assert created["inviteCode"]
    assert created["memberCount"] == 0

    # teacher видит свой класс и код
    response = await client.get(f"{API}/classes", headers=teacher_headers)
    assert response.status_code == 200
    assert any(item["id"] == str(class_id) for item in response.json())

    # ученик вступает по коду; повторный join идемпотентен
    for _ in range(2):
        response = await client.post(
            f"{API}/classes/join",
            json={"inviteCode": created["inviteCode"]},
            headers=student_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["inviteCode"] is None

    response = await client.get(f"{API}/classes", headers=student_headers)
    assert response.status_code == 200
    student_classes = response.json()
    assert len(student_classes) == 1
    assert student_classes[0]["id"] == str(class_id)
    assert student_classes[0]["memberCount"] == 1
    assert student_classes[0]["inviteCode"] is None

    # ученик видит класс, но не roster
    response = await client.get(f"{API}/classes/{class_id}", headers=student_headers)
    assert response.status_code == 200
    assert response.json()["members"] == []

    # teacher видит roster
    response = await client.get(f"{API}/classes/{class_id}", headers=teacher_headers)
    assert response.status_code == 200
    members = response.json()["members"]
    assert len(members) == 1
    assert members[0]["userId"] == str(student_id)
    assert members[0]["email"] == unique_email

    # дашборд: навыки/флаги/матчи
    response = await client.get(
        f"{API}/classes/{class_id}/dashboard", headers=teacher_headers
    )
    assert response.status_code == 200, response.text
    dashboard = response.json()
    assert dashboard["memberCount"] == 1
    member = dashboard["members"][0]
    assert member["userId"] == str(student_id)
    assert len(member["skills"]) == 11
    assert member["flagsCount"] == 0
    assert member["matchesCount"] == 0
    assert member["elo"] == 1000.0

    # ученик не может создавать класс и смотреть дашборд
    response = await client.post(
        f"{API}/classes", json={"name": "Чужой класс"}, headers=student_headers
    )
    assert response.status_code == 403
    response = await client.get(
        f"{API}/classes/{class_id}/dashboard", headers=student_headers
    )
    assert response.status_code == 403


async def test_class_manage_and_foreign_teacher_forbidden(
    admin_client, make_client, unique_email
):
    _ = admin_client
    client = await make_client()
    owner_headers, _owner_id = await _teacher(client, f"owner-{unique_email}")
    foreign_headers, _foreign_id = await _teacher(client, f"foreign-{unique_email}")
    student_email = f"s-{unique_email}"
    student_headers, student_id = await _student(client, student_email)

    response = await client.post(
        f"{API}/classes", json={"name": "Класс owner"}, headers=owner_headers
    )
    assert response.status_code == 201
    class_id = int(response.json()["id"])
    old_code = response.json()["inviteCode"]

    # чужой teacher: 403 на детали/дашборд/мутации
    for method, path, body in (
        ("get", f"{API}/classes/{class_id}", None),
        ("get", f"{API}/classes/{class_id}/dashboard", None),
        ("post", f"{API}/classes/{class_id}/members", {"email": student_email}),
        ("post", f"{API}/classes/{class_id}/invite", None),
    ):
        response = await getattr(client, method)(
            path, headers=foreign_headers, **({"json": body} if body else {})
        )
        assert response.status_code == 403, (method, path, response.text)

    # owner добавляет ученика по email; duplicate — 409
    response = await client.post(
        f"{API}/classes/{class_id}/members",
        json={"email": student_email},
        headers=owner_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["userId"] == str(student_id)
    response = await client.post(
        f"{API}/classes/{class_id}/members",
        json={"email": student_email},
        headers=owner_headers,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "class_member_exists"

    # несуществующий пользователь и не-ученик
    response = await client.post(
        f"{API}/classes/{class_id}/members",
        json={"email": "nobody@e2e.chessclass"},
        headers=owner_headers,
    )
    assert response.status_code == 404
    response = await client.post(
        f"{API}/classes/{class_id}/members",
        json={"email": f"owner-{unique_email}"},
        headers=owner_headers,
    )
    assert response.status_code == 422

    # удаление ученика
    response = await client.delete(
        f"{API}/classes/{class_id}/members/{student_id}", headers=owner_headers
    )
    assert response.status_code == 204
    response = await client.get(f"{API}/classes/{class_id}", headers=owner_headers)
    assert response.json()["members"] == []

    # ротация кода: старый не работает, новый работает
    response = await client.post(
        f"{API}/classes/{class_id}/invite", headers=owner_headers
    )
    assert response.status_code == 200
    new_code = response.json()["inviteCode"]
    assert new_code and new_code != old_code
    response = await client.post(
        f"{API}/classes/join",
        json={"inviteCode": old_code},
        headers=student_headers,
    )
    assert response.status_code == 404
    response = await client.post(
        f"{API}/classes/join",
        json={"inviteCode": new_code},
        headers=student_headers,
    )
    assert response.status_code == 200
