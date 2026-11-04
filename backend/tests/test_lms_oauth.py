"""S-67: OAuth2 client_credentials (Bearer, кэш/refresh), Basic-fallback,
CRUD курсов/маппинга классов, влияние маппинга на activity id statements."""

import time
import uuid
from typing import Any

import httpx
import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from domains.auth.models import User, UserRole
from domains.classes.models import ClassMember, Classroom
from domains.lms import service as svc
from domains.lms.models import LmsClassMap, LmsCourse
from tests.conftest import API


def _handler(state: dict[str, Any]):
    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth/token") and request.method == "POST":
            state["token_calls"] += 1
            form = request.content.decode()
            assert "grant_type=client_credentials" in form
            assert "client_id=cid" in form
            assert "client_secret=s3cret" in form
            assert "scope=lms.writer" in form
            return httpx.Response(
                200,
                json={
                    "access_token": f"tok{state['token_calls']}",
                    "expires_in": 3600,
                },
            )
        if path.endswith("/statements") and request.method == "PUT":
            state["statements"].append(
                {"auth": request.headers.get("authorization")}
            )
            return httpx.Response(204)
        return httpx.Response(500)

    return handler


def _patch_transport(monkeypatch, state: dict[str, Any]) -> None:
    transport = httpx.MockTransport(_handler(state))

    def fake_client(_base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=15.0)

    monkeypatch.setattr(svc, "_http_client", fake_client)


async def test_oauth2_token_cache_refresh_and_send(monkeypatch) -> None:
    monkeypatch.setattr(settings, "lrs_oauth_client_id", "cid")
    monkeypatch.setattr(settings, "lrs_oauth_client_secret", "s3cret")
    monkeypatch.setattr(
        settings, "lrs_oauth_token_url", "http://127.0.0.1:9/oauth/token"
    )
    monkeypatch.setattr(settings, "lrs_oauth_scope", "lms.writer")
    monkeypatch.setattr(settings, "lrs_enabled", True)
    monkeypatch.setattr(settings, "lrs_endpoint", "http://127.0.0.1:9/lrs")
    monkeypatch.setattr(settings, "lrs_key", "")
    monkeypatch.setattr(settings, "lrs_secret", "")

    state: dict[str, Any] = {"token_calls": 0, "statements": []}
    _patch_transport(monkeypatch, state)

    assert svc.lms_auth_mode() == "oauth2"
    svc._oauth_token.value = ""
    svc._oauth_token.expires_at = 0.0

    first = await svc.auth_headers()
    assert first == {"Authorization": "Bearer tok1"}
    second = await svc.auth_headers()
    assert second == first
    assert svc._oauth_token.expires_at > time.monotonic()

    # Bearer из кэша — token-эндпоинт вызван один раз
    assert state["token_calls"] == 1

    # expiry → refresh: второй токен
    svc._oauth_token.expires_at = time.monotonic() - 1
    third = await svc.auth_headers()
    assert third["Authorization"] == "Bearer tok2"
    assert state["token_calls"] == 2

    # _send уходит с Bearer и не refreshed лишний раз
    status = await svc._send(
        {"id": str(uuid.uuid4()), "actor": {"mbox": "mailto:x@example.com"}}
    )
    assert status == 204
    assert state["statements"][0]["auth"] == third["Authorization"]
    assert state["token_calls"] == 2


async def test_basic_auth_fallback(monkeypatch) -> None:
    monkeypatch.setattr(settings, "lrs_oauth_client_id", "")
    monkeypatch.setattr(settings, "lrs_oauth_token_url", "")
    monkeypatch.setattr(settings, "lrs_key", "basic-key")
    monkeypatch.setattr(settings, "lrs_secret", "basic-secret")
    monkeypatch.setattr(settings, "lrs_enabled", True)
    monkeypatch.setattr(settings, "lrs_endpoint", "http://127.0.0.1:9/lrs")

    state: dict[str, Any] = {"token_calls": 0, "statements": []}
    _patch_transport(monkeypatch, state)

    assert svc.lms_auth_mode() == "basic"
    assert await svc.auth_headers() == {}
    status = await svc._send(
        {"id": str(uuid.uuid4()), "actor": {"mbox": "mailto:x@example.com"}}
    )
    assert status == 204
    assert state["statements"][0]["auth"].startswith("Basic ")
    assert state["token_calls"] == 0


async def test_class_mapping_changes_activity_id(admin_client) -> None:
    _ = admin_client
    classroom_id = course_id = mapping_id = 0
    member_email = ""
    try:
        async with session_factory() as session:
            # ученик с существующим skill statement (данные seeds)
            statements = await svc.build_statements(session)
            skill = next(s for s in statements if "/skills/" in s["object"]["id"])
            member_email = skill["actor"]["mbox"].removeprefix("mailto:")
            user = (
                (
                    await session.execute(
                        sa.select(User).where(User.email == member_email)
                    )
                )
                .scalars()
                .one()
            )

            course = await svc.create_course(
                session,
                external_id=f"sns-67-{uuid.uuid4().hex[:8]}",
                title_ru="S67 курс",
            )
            teacher = (
                (
                    await session.execute(
                        sa.select(User).where(User.role == UserRole.TEACHER)
                    )
                )
                .scalars()
                .one()
            )
            classroom = Classroom(
                name="S67-класс",
                teacher_id=teacher.id,
                invite_code=uuid.uuid4().hex[:12],
            )
            session.add(classroom)
            await session.flush()
            session.add(
                ClassMember(class_id=classroom.id, user_id=user.id)
            )
            mapping = await svc.create_class_map(
                session,
                class_id=classroom.id,
                course_id=course.id,
                activity_ref="https://lms.example/s67/courses/42",
            )
            await session.commit()
            classroom_id, course_id, mapping_id = (
                classroom.id,
                course.id,
                mapping.id,
            )
        async with session_factory() as session:
            statements = await svc.build_statements(session)
            mapped = [
                s
                for s in statements
                if s["actor"]["mbox"] == f"mailto:{member_email}"
                and "https://lms.example/s67/courses/42/skills/" in s["object"][
                    "id"
                ]
            ]
            assert mapped, "mapped skill statement должен ссылаться на курс LMS"
            slug = mapped[0]["object"]["id"].rsplit("/", 1)[1]
            assert svc.skill_activity_id(
                "https://lms.example/s67/courses/42", slug
            ) == mapped[0]["object"]["id"]
            # без маппинга — прежний корень
            assert (
                svc.skill_activity_id(None, slug)
                == f"https://chessclass.local/skills/{slug}"
            )
    finally:
        async with session_factory() as session:
            await session.execute(
                sa.delete(ClassMember).where(
                    ClassMember.class_id == classroom_id
                )
            )
            await session.execute(
                sa.delete(LmsClassMap).where(LmsClassMap.id == mapping_id)
            )
            await session.execute(
                sa.delete(Classroom).where(Classroom.id == classroom_id)
            )
            await session.execute(
                sa.delete(LmsCourse).where(LmsCourse.id == course_id)
            )
            await session.commit()


async def test_courses_and_class_map_api(admin_client) -> None:
    # валидация тела
    response = await admin_client.post(
        f"{API}/admin/lms/courses", json={"externalId": "", "titleRu": "x"}
    )
    assert response.status_code == 400

    # курсы: create / dup 409 / list
    external_id = f"api-67-{uuid.uuid4().hex[:8]}"
    response = await admin_client.post(
        f"{API}/admin/lms/courses",
        json={"externalId": external_id, "titleRu": "API курс"},
    )
    assert response.status_code == 201, response.text
    course_id = response.json()["id"]
    response = await admin_client.post(
        f"{API}/admin/lms/courses",
        json={"externalId": external_id, "titleRu": "дубль"},
    )
    assert response.status_code == 409
    response = await admin_client.get(f"{API}/admin/lms/courses")
    assert response.status_code == 200
    assert any(c["externalId"] == external_id for c in response.json())

    # oauth-status — режим виден админу (без сетевых вызовов)
    response = await admin_client.get(f"{API}/admin/lms/oauth-status")
    assert response.status_code == 200
    assert response.json()["mode"] in ("oauth2", "basic", "none")

    # маппинг: валидация и 404 на несуществующий класс
    response = await admin_client.post(
        f"{API}/admin/lms/class-map",
        json={"classId": 1, "courseId": course_id, "activityRef": "no-url"},
    )
    assert response.status_code == 400
    response = await admin_client.post(
        f"{API}/admin/lms/class-map",
        json={
            "classId": 987654321,
            "courseId": course_id,
            "activityRef": "https://lms.example/api-course",
        },
    )
    assert response.status_code == 404

    # реальный класс (прямо в БД) → полный цикл маппинга
    async with session_factory() as session:
        teacher = (
            await session.execute(
                sa.select(User).where(User.email == "teacher@chessclass.dev")
            )
        ).scalar_one()
        classroom = Classroom(
            name="API S67 класс",
            teacher_id=teacher.id,
            invite_code=uuid.uuid4().hex[:12],
        )
        session.add(classroom)
        await session.flush()
        class_id = classroom.id
        await session.commit()
    try:
        response = await admin_client.post(
            f"{API}/admin/lms/class-map",
            json={
                "classId": class_id,
                "courseId": course_id,
                "activityRef": "https://lms.example/api-course",
            },
        )
        assert response.status_code == 201, response.text
        map_id = response.json()["id"]
        assert response.json()["courseTitle"] == "API курс"

        response = await admin_client.post(
            f"{API}/admin/lms/class-map",
            json={
                "classId": class_id,
                "courseId": course_id,
                "activityRef": "https://lms.example/api-course-2",
            },
        )
        assert response.status_code == 409  # один класс — один маппинг

        response = await admin_client.get(f"{API}/admin/lms/class-map")
        assert response.status_code == 200
        rows = [r for r in response.json() if r["id"] == map_id]
        assert rows and rows[0]["className"] == "API S67 класс"

        response = await admin_client.delete(f"{API}/admin/lms/class-map/{map_id}")
        assert response.status_code == 204
    finally:
        async with session_factory() as session:
            await session.execute(
                sa.delete(Classroom).where(Classroom.id == class_id)
            )
            await session.commit()

    response = await admin_client.delete(f"{API}/admin/lms/courses/{course_id}")
    assert response.status_code == 204
    response = await admin_client.delete(f"{API}/admin/lms/courses/{course_id}")
    assert response.status_code == 404
