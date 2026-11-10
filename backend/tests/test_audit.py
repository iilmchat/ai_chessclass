"""S-41: auditor read-only + audit_log + CSV."""

from decimal import Decimal

from core.db import session_factory
from domains.anticheat.models import (
    AnticheatFlag,
    FlagDomain,
    FlagKind,
    FlagStatus,
)
from domains.auth.models import UserRole
from tests.conftest import API, login, make_direct_user


async def _headers(client, email: str, role: UserRole):
    await make_direct_user(email, role)
    _client, access, user_id = await login(client, email)
    return {"Authorization": f"Bearer {access}"}, user_id


async def test_auditor_reads_and_teacher_actions_are_logged(
    admin_client, make_client, unique_email
):
    _ = admin_client
    client = await make_client()
    teacher_headers, teacher_id = await _headers(
        client, f"t-{unique_email}", UserRole.TEACHER
    )
    auditor_headers, auditor_id = await _headers(
        client, f"a-{unique_email}", UserRole.AUDITOR
    )
    # S-91: auditor scope fail-closed — выдаём явные права admin'ом.
    response = await admin_client.patch(
        f"{API}/admin/users/{auditor_id}/auditor-scope",
        json={"scopes": {"audit": True, "reports": True, "flags": True}},
    )
    assert response.status_code == 200, response.text
    student_email = f"s-{unique_email}"
    student_headers, student_id = await _headers(
        client, student_email, UserRole.STUDENT
    )

    # действия учителя: класс + ученик + review флага + PDF
    response = await client.post(
        f"{API}/classes", json={"name": "Аудит-класс"}, headers=teacher_headers
    )
    assert response.status_code == 201, response.text
    class_id = int(response.json()["id"])

    response = await client.post(
        f"{API}/classes/{class_id}/members",
        json={"email": student_email},
        headers=teacher_headers,
    )
    assert response.status_code == 201, response.text

    async with session_factory() as session:
        flag = AnticheatFlag(
            user_id=student_id,
            kind=FlagKind.ENGINE_LIKELINESS,
            domain=FlagDomain.CHESS,
            confidence=Decimal("0.90"),
            evidence={"source": "test"},
            status=FlagStatus.NEW,
        )
        session.add(flag)
        await session.commit()
        flag_id = int(flag.id)

    response = await client.post(
        f"{API}/admin/anticheat/flags/{flag_id}/review",
        json={"status": "reviewed", "note": "проверено"},
        headers=teacher_headers,
    )
    assert response.status_code == 200, response.text

    response = await client.post(
        f"{API}/reports/pdf/{student_id}", headers=teacher_headers
    )
    assert response.status_code == 201, response.text
    report_id = int(response.json()["reportId"])

    # auditor читает журнал и фильтрует по действию
    response = await client.get(
        f"{API}/admin/audit/logs",
        params={"actorId": teacher_id, "action": "classes.create"},
        headers=auditor_headers,
    )
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] >= 1
    assert all(item["action"] == "classes.create" for item in page["items"])
    assert page["items"][0]["actorId"] == str(teacher_id)
    assert page["items"][0]["actorRole"] == "teacher"

    response = await client.get(
        f"{API}/admin/audit/logs", params={"actorId": teacher_id},
        headers=auditor_headers,
    )
    actions = {item["action"] for item in response.json()["items"]}
    assert {
        "classes.create",
        "classes.member.add",
        "anticheat.flag.review",
        "reports.pdf.generate",
    } <= actions

    # auditor читает флаги/вердикты/PDF
    assert (
        await client.get(f"{API}/admin/anticheat/flags", headers=auditor_headers)
    ).status_code == 200
    assert (
        await client.get(f"{API}/admin/anticheat/judge", headers=auditor_headers)
    ).status_code == 200
    response = await client.get(
        f"{API}/reports/pdf/{report_id}", headers=auditor_headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")

    # auditor не меняет данные
    response = await client.post(
        f"{API}/admin/anticheat/flags/{flag_id}/review",
        json={"status": "confirmed"},
        headers=auditor_headers,
    )
    assert response.status_code == 403
    response = await client.post(
        f"{API}/reports/pdf/{student_id}", headers=auditor_headers
    )
    assert response.status_code == 403
    response = await client.post(
        f"{API}/classes", json={"name": "Нельзя"}, headers=auditor_headers
    )
    assert response.status_code == 403

    # студент не читает аудит
    response = await client.get(f"{API}/admin/audit/logs", headers=student_headers)
    assert response.status_code == 403

    # CSV-экспорт auditor
    response = await client.get(
        f"{API}/admin/audit/export.csv", headers=auditor_headers
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "classes.create" in response.text
    assert "attachment; filename=" in response.headers["content-disposition"]

    # экспорт залогирован
    response = await client.get(
        f"{API}/admin/audit/logs",
        params={"action": "audit.export", "actorId": auditor_id},
        headers=auditor_headers,
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1
