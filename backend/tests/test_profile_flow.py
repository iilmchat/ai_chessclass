"""E2E профиль (DoD S-03): /profile/me, PATCH, RBAC (teacher видит учеников),
смена уровня админом → уровень попадает в JWT, /readyz."""

from core.security import decode_token
from domains.auth.models import UserRole
from tests.conftest import API, login, make_direct_user, register_verified


async def _bearer_headers(access: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access}"}


async def test_profile_me_and_patch(make_client, unique_email):
    client = await make_client()
    registered = await register_verified(client, unique_email)
    _client, access, _user_id = await login(client, unique_email)
    headers = await _bearer_headers(access)

    # профиль создан при регистрации: novice/free
    response = await client.get(f"{API}/profile/me", headers=headers)
    assert response.status_code == 200
    profile = response.json()
    assert profile["id"] == registered["id"]
    assert profile["level"] == "novice"
    assert profile["billingTier"] == "free"
    assert profile["displayName"] is None
    assert profile["emailVerified"] is True

    # PATCH: только displayName/prefs; level здесь не меняется
    response = await client.patch(
        f"{API}/profile/me", json={"displayName": "Вася Пупкин"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["displayName"] == "Вася Пупкин"
    assert response.json()["level"] == "novice"

    # access-JWT несёт уровень профиля (Design §13.1: sub/role/level)
    payload = decode_token(access)
    assert payload is not None and payload["level"] == "novice"


async def test_rbac_profile_endpoints(make_client, unique_email):
    client = await make_client()
    registered = await register_verified(client, unique_email)
    student_id = int(registered["id"])
    _client, student_access, _ = await login(client, unique_email)
    headers = await _bearer_headers(student_access)

    # student не видит список учеников и чужие профили
    response = await client.get(f"{API}/profile/students", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "auth_forbidden"
    response = await client.get(f"{API}/profile/1", headers=headers)
    assert response.status_code == 403

    # teacher видит список учеников и профиль конкретного ученика
    teacher_email = f"t-{unique_email}"
    await make_direct_user(teacher_email, UserRole.TEACHER)
    _client, teacher_access, _ = await login(client, teacher_email)
    teacher_headers = await _bearer_headers(teacher_access)

    # S-91: teacher видит учеников только своих классов.
    response = await client.post(
        f"{API}/classes", json={"name": "Профиль-класс"}, headers=teacher_headers
    )
    assert response.status_code == 201
    class_id = int(response.json()["id"])
    response = await client.post(
        f"{API}/classes/{class_id}/members",
        json={"email": unique_email},
        headers=teacher_headers,
    )
    assert response.status_code == 201

    response = await client.get(f"{API}/profile/students", headers=teacher_headers)
    assert response.status_code == 200
    page = response.json()
    assert page["total"] >= 1
    assert any(item["email"] == unique_email for item in page["items"])

    response = await client.get(
        f"{API}/profile/{student_id}", headers=teacher_headers
    )
    assert response.status_code == 200
    assert response.json()["email"] == unique_email

    # teacher не может менять уровень (только admin)
    response = await client.patch(
        f"{API}/profile/{student_id}/level",
        json={"level": "advanced"},
        headers=teacher_headers,
    )
    assert response.status_code == 403


async def test_admin_sets_level_and_jwt_reflects_it(admin_client, make_client, unique_email):
    _ = admin_client  # ensure seeds + admin login
    client = await make_client()
    registered = await register_verified(client, unique_email)
    student_id = int(registered["id"])
    _client, access_before, _ = await login(client, unique_email)

    # admin меняет уровень
    response = await admin_client.patch(
        f"{API}/profile/{student_id}/level", json={"level": "advanced"}
    )
    assert response.status_code == 200
    assert response.json()["level"] == "advanced"

    # старый JWT — ещё старый уровень; после перелогина — новый
    payload_before = decode_token(access_before)
    assert payload_before is not None and payload_before["level"] == "novice"
    _client, access_after, _ = await login(client, unique_email)
    payload_after = decode_token(access_after)
    assert payload_after is not None and payload_after["level"] == "advanced"


async def test_students_pagination(make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    teacher_email = f"t-{unique_email}"
    await make_direct_user(teacher_email, UserRole.TEACHER)
    _client, teacher_access, _ = await login(client, teacher_email)
    headers = await _bearer_headers(teacher_access)

    response = await client.post(
        f"{API}/classes", json={"name": "Пагинация-класс"}, headers=headers
    )
    assert response.status_code == 201
    class_id = int(response.json()["id"])
    response = await client.post(
        f"{API}/classes/{class_id}/members",
        json={"email": unique_email},
        headers=headers,
    )
    assert response.status_code == 201

    response = await client.get(
        f"{API}/profile/students", params={"page": 1, "pageSize": 1}, headers=headers
    )
    assert response.status_code == 200
    page = response.json()
    assert len(page["items"]) == 1
    assert page["page"] == 1 and page["pageSize"] == 1
    assert page["total"] >= 1


async def test_readyz_details(make_client):
    client = await make_client()
    response = await client.get(f"{API}/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    from app import __version__ as app_version

    assert body["version"] == app_version
    assert body["db"]["ok"] is True
    assert body["db"]["migrationsUpToDate"] is True
    assert body["db"]["revision"] == body["db"]["head"]
    assert body["redis"] is True
