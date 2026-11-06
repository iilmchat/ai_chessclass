"""S-83: подтверждение возрастной группы ученика учителем.

Consent enforcement v0.6.1: учитель класса — доверенный источник age_group;
подтверждение видно в consent status и roster, self-change учеником сбрасывает
подтверждение (и пишется в audit).
"""

import sqlalchemy as sa

from core.db import session_factory
from domains.audit.models import AuditLog
from domains.auth.models import UserRole
from tests.conftest import API, login, make_direct_user

CONFIRM_ACTION = "classes.student.age_group.confirm"


async def _user(client, email: str, role: UserRole):
    await make_direct_user(email, role)
    _client, access, user_id = await login(client, email)
    return {"Authorization": f"Bearer {access}"}, user_id


async def _class_with_student(client, teacher_headers: dict, student_email: str) -> int:
    response = await client.post(
        f"{API}/classes", json={"name": "S-83 класс"}, headers=teacher_headers
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


async def _audit_actions(target_id: int) -> list[str]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                sa.select(AuditLog.action).where(
                    AuditLog.target_type == "user",
                    AuditLog.target_id == str(target_id),
                )
            )
        ).scalars()
        return list(rows)


async def _confirm(client, class_id: int, student_id: int, age_group: str, headers: dict):
    return await client.post(
        f"{API}/classes/{class_id}/students/{student_id}/age-group",
        json={"ageGroup": age_group},
        headers=headers,
    )


async def test_teacher_confirms_age_group(make_client, unique_email):
    client = await make_client()
    teacher_headers, teacher_id = await _user(
        client, f"t-{unique_email}", UserRole.TEACHER
    )
    student_headers, student_id = await _user(client, unique_email, UserRole.STUDENT)
    class_id = await _class_with_student(client, teacher_headers, unique_email)

    # self-declared child: согласие нужно, но учитель ещё не подтвердил
    response = await client.patch(
        f"{API}/profile/me", json={"ageGroup": "child"}, headers=student_headers
    )
    assert response.status_code == 200, response.text
    status = (await client.get(f"{API}/consent/status", headers=student_headers)).json()
    assert status["required"] is True
    assert status["teacherConfirmed"] is False
    assert status["ageGroup"] == "child"
    assert status["ageGroupConfirmedAt"] is None

    # учитель класса подтверждает child
    response = await _confirm(client, class_id, student_id, "child", teacher_headers)
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["userId"] == str(student_id)
    assert confirmed["ageGroup"] == "child"
    assert confirmed["confirmedBy"] == str(teacher_id)
    assert confirmed["confirmedAt"]

    # roster (GET /classes/{id}) показывает возраст и подтверждение
    detail = (
        await client.get(f"{API}/classes/{class_id}", headers=teacher_headers)
    ).json()
    member = next(item for item in detail["members"] if item["userId"] == str(student_id))
    assert member["ageGroup"] == "child"
    assert member["ageGroupConfirmedAt"] is not None

    # consent status: подтверждение учителем видно, согласие по-прежнему нужно
    status = (await client.get(f"{API}/consent/status", headers=student_headers)).json()
    assert status["teacherConfirmed"] is True
    assert status["ageGroup"] == "child"
    assert status["ageGroupConfirmedAt"] is not None
    assert status["required"] is True

    # учитель подтверждает adult: parental consent больше не требуется
    response = await _confirm(client, class_id, student_id, "adult", teacher_headers)
    assert response.status_code == 200, response.text
    status = (await client.get(f"{API}/consent/status", headers=student_headers)).json()
    assert status["required"] is False
    assert status["status"] == "not_required"
    assert status["teacherConfirmed"] is True
    assert status["ageGroup"] == "adult"

    actions = await _audit_actions(student_id)
    assert actions.count(CONFIRM_ACTION) == 2
    assert "profile.age_group" in actions


async def test_age_confirmation_access_control(admin_client, make_client, unique_email):
    client = await make_client()
    owner_headers, _owner_id = await _user(
        client, f"owner-{unique_email}", UserRole.TEACHER
    )
    foreign_headers, _foreign_id = await _user(
        client, f"foreign-{unique_email}", UserRole.TEACHER
    )
    student_headers, student_id = await _user(client, unique_email, UserRole.STUDENT)
    _other_headers, other_student_id = await _user(
        client, f"other-{unique_email}", UserRole.STUDENT
    )
    class_id = await _class_with_student(client, owner_headers, unique_email)

    # чужой учитель — 403
    response = await _confirm(client, class_id, student_id, "teen", foreign_headers)
    assert response.status_code == 403, response.text

    # ученик не может подтверждать (нет роли teacher) — 403
    response = await _confirm(client, class_id, student_id, "teen", student_headers)
    assert response.status_code == 403, response.text

    # существующий, но не участник класса — 404
    response = await _confirm(
        client, class_id, other_student_id, "teen", owner_headers
    )
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "class_member_not_found"

    # несуществующий ученик — 404
    response = await _confirm(client, class_id, 999_999_999, "teen", owner_headers)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "user_not_found"

    # admin может подтвердить возраст в любом классе
    response = await admin_client.post(
        f"{API}/classes/{class_id}/students/{student_id}/age-group",
        json={"ageGroup": "teen"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ageGroup"] == "teen"


async def test_self_age_change_resets_teacher_confirmation(make_client, unique_email):
    client = await make_client()
    teacher_headers, _teacher_id = await _user(
        client, f"t-{unique_email}", UserRole.TEACHER
    )
    student_headers, student_id = await _user(client, unique_email, UserRole.STUDENT)
    class_id = await _class_with_student(client, teacher_headers, unique_email)

    response = await _confirm(client, class_id, student_id, "teen", teacher_headers)
    assert response.status_code == 200, response.text

    # self-PATCH тем же значением не сбрасывает подтверждение
    response = await client.patch(
        f"{API}/profile/me", json={"ageGroup": "teen"}, headers=student_headers
    )
    assert response.status_code == 200, response.text
    status = (await client.get(f"{API}/consent/status", headers=student_headers)).json()
    assert status["teacherConfirmed"] is True

    # self-PATCH другим значением сбрасывает trusted-метку
    response = await client.patch(
        f"{API}/profile/me", json={"ageGroup": "child"}, headers=student_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["ageGroup"] == "child"
    status = (await client.get(f"{API}/consent/status", headers=student_headers)).json()
    assert status["teacherConfirmed"] is False
    assert status["ageGroupConfirmedAt"] is None
    assert status["ageGroup"] == "child"
    assert status["required"] is True

    actions = await _audit_actions(student_id)
    assert "profile.age_group" in actions
    assert actions.count(CONFIRM_ACTION) == 1


async def test_consent_email_smtp_failure_stays_queued(
    make_client, unique_email, monkeypatch
):
    """S-83: ошибка SMTP не рвёт запрос — письмо уходит в email_outbox."""
    from domains.notifications import service as notifications_svc
    from domains.notifications.models import EmailOutbox

    parent = f"parent-{unique_email}"
    client = await make_client()
    headers, _user_id = await _user(client, unique_email, UserRole.STUDENT)
    response = await client.patch(
        f"{API}/profile/me", json={"ageGroup": "child"}, headers=headers
    )
    assert response.status_code == 200, response.text

    async def broken_send(to: str, subject: str, text: str) -> bool:
        raise OSError("smtp down")

    monkeypatch.setattr(notifications_svc, "send_email", broken_send)

    response = await client.post(
        f"{API}/consent/request", json={"parentEmail": parent}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["emailDelivered"] is False
    assert body["emailQueued"] is True

    async with session_factory() as session:
        row = (
            await session.execute(
                sa.select(EmailOutbox)
                .where(EmailOutbox.recipient == parent)
                .order_by(EmailOutbox.id.desc())
            )
        ).scalars().first()
        assert row is not None
        assert row.status == "failed"
        assert row.attempts == 1
        assert row.next_attempt_at is not None
        assert "smtp down" in (row.last_error or "")
        await session.execute(
            sa.delete(EmailOutbox).where(EmailOutbox.recipient == parent)
        )
        await session.commit()
