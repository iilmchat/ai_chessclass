"""S-91: object-level authorization (BOLA) — кросс-тенантные API-тесты.

Все тесты используют реальные RS256 access-JWT (ключи генерируются в
autouse-фикстуре), а не mock-токены.
"""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from core.config import settings
from tests.conftest import API, login, make_direct_user, register_verified

RANDOM_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)
GOOD_PGN = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"


@pytest.fixture(autouse=True)
def rs256_jwt(monkeypatch):
    """S-91 DoD: тесты идут с настоящими RS256-токенами."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setattr(settings, "jwt_algorithm", "RS256")
    monkeypatch.setattr(settings, "jwt_private_key", private)
    monkeypatch.setattr(settings, "jwt_public_key", public)
    monkeypatch.setattr(settings, "jwt_private_key_path", "")
    monkeypatch.setattr(settings, "jwt_public_key_path", "")
    monkeypatch.setattr(settings, "jwt_kid", "s91-test")
    monkeypatch.setattr(settings, "jwt_legacy_hs256", False)


def _headers(access: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access}"}


async def _user(client, email: str, role: str):
    from domains.auth.models import UserRole

    if role == "student":
        await register_verified(client, email)
    else:
        await make_direct_user(email, UserRole(role))
    _c, access, user_id = await login(client, email)
    return _headers(access), user_id


async def _class_with_student(
    client, teacher_headers, name: str, student_email: str
) -> int:
    response = await client.post(
        f"{API}/classes", json={"name": name}, headers=teacher_headers
    )
    assert response.status_code == 201, response.text
    class_id = int(response.json()["id"])
    response = await client.post(
        f"{API}/classes/{class_id}/members",
        json={"email": student_email},
        headers=teacher_headers,
    )
    assert response.status_code == 201, response.text
    return class_id


async def test_pdf_cross_tenant_teacher_forbidden(make_client, unique_email):
    client = await make_client()
    teacher_a, _ = await _user(client, f"pdf-a-{unique_email}", "teacher")
    teacher_b, _ = await _user(client, f"pdf-b-{unique_email}", "teacher")
    student_h, student_id = await _user(client, f"pdf-s-{unique_email}", "student")
    admin_h, _ = await _user(client, f"pdf-admin-{unique_email}", "admin")

    await _class_with_student(
        client, teacher_a, "PDF A", f"pdf-s-{unique_email}"
    )

    response = await client.post(
        f"{API}/reports/pdf/{student_id}", headers=teacher_a
    )
    assert response.status_code == 201, response.text
    report_id = int(response.json()["reportId"])

    response = await client.get(f"{API}/reports/pdf/{report_id}", headers=teacher_b)
    assert response.status_code == 403, response.text

    response = await client.get(f"{API}/reports/pdf/{report_id}", headers=teacher_a)
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")

    response = await client.get(f"{API}/reports/pdf/{report_id}", headers=student_h)
    assert response.status_code == 200

    response = await client.get(f"{API}/reports/pdf/{report_id}", headers=admin_h)
    assert response.status_code == 200


async def test_audit_scope_and_teacher_isolation(make_client, unique_email):
    client = await make_client()
    teacher_a, teacher_a_id = await _user(
        client, f"aud-a-{unique_email}", "teacher"
    )
    teacher_b, teacher_b_id = await _user(
        client, f"aud-b-{unique_email}", "teacher"
    )
    auditor_h, auditor_id = await _user(
        client, f"aud-r-{unique_email}", "auditor"
    )
    admin_h, _ = await _user(client, f"aud-admin-{unique_email}", "admin")

    await client.post(f"{API}/classes", json={"name": "Audit A"}, headers=teacher_a)
    await client.post(f"{API}/classes", json={"name": "Audit B"}, headers=teacher_b)

    # Аудитор без scope audit — fail-closed.
    response = await client.get(f"{API}/admin/audit/logs", headers=auditor_h)
    assert response.status_code == 403

    response = await client.patch(
        f"{API}/admin/users/{auditor_id}/auditor-scope",
        json={"scopes": {"audit": True, "reports": True, "flags": True}},
        headers=admin_h,
    )
    assert response.status_code == 200, response.text

    response = await client.get(
        f"{API}/admin/audit/logs", params={"pageSize": 200}, headers=auditor_h
    )
    assert response.status_code == 200, response.text
    actors = {item["actorId"] for item in response.json()["items"]}
    assert str(teacher_a_id) in actors and str(teacher_b_id) in actors

    # Учитель A видит только собственные действия, не действия учителя B.
    response = await client.get(
        f"{API}/admin/audit/logs", params={"pageSize": 200}, headers=teacher_a
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items
    assert all(item["actorId"] == str(teacher_a_id) for item in items)


async def test_bot_cross_tenant_forbidden(make_client, unique_email):
    client = await make_client()
    student_a, _ = await _user(client, f"bot-a-{unique_email}", "student")
    student_b, _ = await _user(client, f"bot-b-{unique_email}", "student")

    response = await client.post(
        f"{API}/bots",
        json={"code": RANDOM_BOT, "entry": "choose_move"},
        headers=student_a,
    )
    assert response.status_code == 201, response.text
    bot_id = int(response.json()["id"])

    response = await client.get(f"{API}/bots/{bot_id}", headers=student_b)
    assert response.status_code == 403, response.text
    response = await client.get(f"{API}/bots/{bot_id}/matches", headers=student_b)
    assert response.status_code == 403, response.text

    response = await client.get(f"{API}/bots/{bot_id}/matches", headers=student_a)
    assert response.status_code == 200


async def test_chess_game_cross_tenant_forbidden(make_client, unique_email):
    client = await make_client()
    student_a, _ = await _user(client, f"game-a-{unique_email}", "student")
    student_b, _ = await _user(client, f"game-b-{unique_email}", "student")

    response = await client.post(
        f"{API}/chess/games/upload", json={"pgn": GOOD_PGN}, headers=student_a
    )
    assert response.status_code == 202, response.text
    game_id = int(response.json()["gameId"])

    response = await client.get(f"{API}/chess/games/{game_id}", headers=student_b)
    assert response.status_code == 403, response.text
    response = await client.get(
        f"{API}/chess/games/{game_id}/blunders", headers=student_b
    )
    assert response.status_code == 403, response.text
    response = await client.get(f"{API}/chess/games/{game_id}", headers=student_a)
    assert response.status_code == 200


async def test_submission_cross_tenant_forbidden(make_client, unique_email):
    client = await make_client()
    admin_h, _ = await _user(client, f"sub-admin-{unique_email}", "admin")
    response = await client.post(
        f"{API}/py/assignments",
        json={
            "slug": f"authz-{unique_email.split('@')[0]}",
            "title": "Authz",
            "level": "novice",
            "topic": "conditions",
            "statement": "Напиши greet(name).",
            "starterCode": "def greet(name):\n    pass\n",
            "tests": ['assert greet("A") == "Привет, A!"'],
        },
        headers=admin_h,
    )
    assert response.status_code == 201, response.text
    assignment_id = int(response.json()["id"])

    student_a_h, _ = await _user(client, f"sub-a-{unique_email}", "student")
    student_b_h, _ = await _user(client, f"sub-b-{unique_email}", "student")
    teacher_a, _ = await _user(client, f"sub-t-a-{unique_email}", "teacher")
    teacher_b, _ = await _user(client, f"sub-t-b-{unique_email}", "teacher")
    await _class_with_student(
        client, teacher_a, "Sub A", f"sub-a-{unique_email}"
    )

    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": 'def greet(name):\n    return f"Привет, {name}!"\n'},
        headers=student_a_h,
    )
    assert response.status_code == 200, response.text
    submission_id = int(response.json()["id"])

    assert (
        await client.get(
            f"{API}/py/submissions/{submission_id}", headers=teacher_a
        )
    ).status_code == 200
    assert (
        await client.get(
            f"{API}/py/submissions/{submission_id}", headers=teacher_b
        )
    ).status_code == 403
    assert (
        await client.get(
            f"{API}/py/submissions/{submission_id}", headers=student_b_h
        )
    ).status_code == 403
    assert (
        await client.get(f"{API}/py/submissions/{submission_id}", headers=admin_h)
    ).status_code == 200


async def test_pvp_room_cross_tenant_forbidden(make_client, unique_email):
    client = await make_client()
    student_a_h, _ = await _user(client, f"pvp-a-{unique_email}", "student")
    student_b_h, _ = await _user(client, f"pvp-b-{unique_email}", "student")

    response = await client.post(
        f"{API}/bots",
        json={"code": RANDOM_BOT, "entry": "choose_move"},
        headers=student_a_h,
    )
    bot_id = int(response.json()["id"])
    response = await client.post(
        f"{API}/pvp/rooms", json={"botVersionId": bot_id}, headers=student_a_h
    )
    assert response.status_code == 201, response.text
    room_id = int(response.json()["id"])

    assert (
        await client.get(f"{API}/pvp/rooms/{room_id}", headers=student_a_h)
    ).status_code == 200
    assert (
        await client.get(f"{API}/pvp/rooms/{room_id}", headers=student_b_h)
    ).status_code == 403


async def test_student_profile_cross_tenant_forbidden(make_client, unique_email):
    client = await make_client()
    student_h, student_id = await _user(client, f"prof-s-{unique_email}", "student")
    teacher_a, _ = await _user(client, f"prof-a-{unique_email}", "teacher")
    teacher_b, _ = await _user(client, f"prof-b-{unique_email}", "teacher")
    admin_h, _ = await _user(client, f"prof-admin-{unique_email}", "admin")
    await _class_with_student(
        client, teacher_a, "Profile A", f"prof-s-{unique_email}"
    )

    assert (
        await client.get(f"{API}/profile/{student_id}", headers=teacher_a)
    ).status_code == 200
    assert (
        await client.get(f"{API}/profile/{student_id}", headers=teacher_b)
    ).status_code == 403
    assert (
        await client.get(f"{API}/progress/{student_id}", headers=teacher_b)
    ).status_code == 403
    assert (
        await client.get(f"{API}/skills/{student_id}", headers=teacher_b)
    ).status_code == 403
    assert (
        await client.get(f"{API}/profile/{student_id}", headers=admin_h)
    ).status_code == 200
    assert (
        await client.get(f"{API}/profile/{student_id}", headers=student_h)
    ).status_code == 403  # student имеет /profile/me, не чужой id
