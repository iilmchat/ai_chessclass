"""S-49: admin API LMS LRS — status, sync, delivery journal/CSV.

S-67: CRUD курсов LMS (`/courses`) и маппинга классов (`/class-map`),
OAuth2-статус (`/oauth-status`) — literal-пути регистрируются до
параметризованных (`/courses/{course_id}`).
"""

import csv
import io
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from core.base import CamelModel
from core.config import settings
from core.errors import AppError
from domains.audit import service as audit_svc
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole
from domains.lms import service as svc
from domains.lms.models import LmsClassMap, LmsCourse, LrsDelivery

router = APIRouter(prefix="/admin/lms", tags=["lms"])
AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]
TeacherOrAdmin = Annotated[
    User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))
]


class LmsStatusOut(CamelModel):
    configured: bool
    endpoint: str | None
    auth_mode: str
    counts: dict[str, int]
    last_delivery: dict | None


class SyncOut(CamelModel):
    queued: int
    sent: int
    failed: int
    pending: int
    disabled: int


class DeliveryOut(CamelModel):
    id: str
    statement_id: str
    status: str
    attempts: int
    response_status: int | None
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


def _delivery_out(row: LrsDelivery) -> DeliveryOut:
    return DeliveryOut(
        id=str(row.id),
        statement_id=row.statement_id,
        status=row.status,
        attempts=row.attempts,
        response_status=row.response_status,
        last_error=row.last_error,
        created_at=row.created_at,
        sent_at=row.sent_at,
    )


@router.get("/status", response_model=LmsStatusOut)
async def lms_status(_guard: AdminOnly, session: DbSession) -> LmsStatusOut:
    return LmsStatusOut(**await svc.status(session))


@router.post("/sync", response_model=SyncOut)
async def lms_sync(
    request: Request, user: AdminOnly, session: DbSession
) -> SyncOut:
    result = await svc.sync(session, redis=request.app.state.redis)
    await audit_svc.record(
        session,
        user,
        "lms.sync",
        target_type="lrs",
        source="api",
        meta=result,
        request=request,
    )
    await session.commit()
    return SyncOut(**result)


@router.get("/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(
    _guard: AdminOnly,
    session: DbSession,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DeliveryOut]:
    rows = await svc.list_deliveries(
        session, status_filter=status, limit=limit
    )
    return [_delivery_out(row) for row in rows]


@router.get("/deliveries.csv")
async def deliveries_csv(
    _guard: AdminOnly,
    session: DbSession,
    status: str | None = Query(default=None),
) -> Response:
    rows = await svc.list_deliveries(session, status_filter=status, limit=5000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "statement_id",
            "status",
            "attempts",
            "response_status",
            "last_error",
            "created_at",
            "sent_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.statement_id,
                row.status,
                row.attempts,
                row.response_status or "",
                row.last_error or "",
                row.created_at.isoformat(),
                row.sent_at.isoformat() if row.sent_at else "",
            ]
        )
    filename = f"lrs-deliveries-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- S-67: курсы LMS, маппинг классов, OAuth2-статус ---


class CourseIn(CamelModel):
    external_id: str
    title_ru: str


class CourseOut(CamelModel):
    id: int
    external_id: str
    title_ru: str


class ClassMapIn(CamelModel):
    class_id: int
    course_id: int
    activity_ref: str


class ClassMapOut(CamelModel):
    id: int
    class_id: int
    course_id: int
    activity_ref: str
    class_name: str
    course_title: str


class OauthStatusOut(CamelModel):
    mode: str
    token_url: str | None = None
    scope: str | None = None


@router.get("/oauth-status", response_model=OauthStatusOut)
async def oauth_status(_guard: AdminOnly) -> OauthStatusOut:
    token_url = settings.lrs_oauth_token_url or None
    return OauthStatusOut(
        mode=svc.lms_auth_mode(),
        token_url=token_url,
        scope=settings.lrs_oauth_scope or None,
    )


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(_guard: TeacherOrAdmin, session: DbSession) -> list[CourseOut]:
    return [
        CourseOut(id=c.id, external_id=c.external_id, title_ru=c.title_ru)
        for c in await svc.list_courses(session)
    ]


@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(
    request: Request, user: AdminOnly, session: DbSession, body: CourseIn
) -> CourseOut:
    external_id = body.external_id.strip()
    if not external_id or not body.title_ru.strip():
        raise AppError("lms_validation", "external_id и title_ru обязательны", 400)
    try:
        course = await svc.create_course(
            session, external_id=external_id, title_ru=body.title_ru.strip()
        )
    except RuntimeError as exc:
        raise AppError("lms_conflict", str(exc), 409) from exc
    await audit_svc.record(
        session,
        user,
        "lms.course.create",
        target_type="lms_course",
        target_id=str(course.id),
        source="api",
        meta={"externalId": course.external_id},
        request=request,
    )
    await session.commit()
    return CourseOut(
        id=course.id, external_id=course.external_id, title_ru=course.title_ru
    )


@router.delete("/courses/{course_id}", status_code=204)
async def delete_course(
    request: Request, user: AdminOnly, session: DbSession, course_id: int
) -> Response:
    deleted = await svc.delete_course(session, course_id)
    if not deleted:
        raise AppError("lms_not_found", f"Курс {course_id} не найден", 404)
    await audit_svc.record(
        session,
        user,
        "lms.course.delete",
        target_type="lms_course",
        target_id=str(course_id),
        source="api",
        request=request,
    )
    await session.commit()
    return Response(status_code=204)


@router.get("/class-map", response_model=list[ClassMapOut])
async def list_class_maps(
    _guard: TeacherOrAdmin, session: DbSession
) -> list[ClassMapOut]:
    return [
        ClassMapOut(
            id=row.map_id,
            class_id=row.class_id,
            course_id=row.course_id,
            activity_ref=row.activity_ref,
            class_name=row.class_name,
            course_title=row.course_title,
        )
        for row in await svc.list_class_maps(session)
    ]


@router.post("/class-map", response_model=ClassMapOut, status_code=201)
async def create_class_map(
    request: Request, user: AdminOnly, session: DbSession, body: ClassMapIn
) -> ClassMapOut:
    if not body.activity_ref.strip().startswith(("http://", "https://")):
        raise AppError(
            "lms_validation", "activity_ref должен быть http(s)-URL", 400
        )
    try:
        mapping = await svc.create_class_map(
            session,
            class_id=body.class_id,
            course_id=body.course_id,
            activity_ref=body.activity_ref.strip(),
        )
    except LookupError as exc:
        raise AppError("lms_not_found", str(exc), 404) from exc
    except KeyError as exc:
        raise AppError("lms_not_found", str(exc), 404) from exc
    except RuntimeError as exc:
        raise AppError("lms_conflict", str(exc), 409) from exc
    await audit_svc.record(
        session,
        user,
        "lms.class_map.create",
        target_type="lms_class_map",
        target_id=str(mapping.id),
        source="api",
        meta={"classId": mapping.class_id, "courseId": mapping.course_id},
        request=request,
    )
    await session.commit()
    class_name, course_title = await _names_for(session, mapping)
    return ClassMapOut(
        id=mapping.id,
        class_id=mapping.class_id,
        course_id=mapping.course_id,
        activity_ref=mapping.activity_ref,
        class_name=class_name,
        course_title=course_title,
    )


async def _names_for(
    session: DbSession, mapping: svc.ClassMapRow | LmsClassMap
) -> tuple[str, str]:
    """Имена класса и курса для ответа create (S-67, без повторного GET)."""
    from sqlalchemy import select as sa_select

    from domains.classes.models import Classroom

    class_name = (
        await session.execute(
            sa_select(Classroom.name).where(Classroom.id == mapping.class_id)
        )
    ).scalar_one_or_none()
    course_title = (
        await session.execute(
            sa_select(LmsCourse.title_ru).where(LmsCourse.id == mapping.course_id)
        )
    ).scalar_one_or_none()
    return class_name or "", course_title or ""


@router.delete("/class-map/{map_id}", status_code=204)
async def delete_class_map(
    request: Request, user: AdminOnly, session: DbSession, map_id: int
) -> Response:
    deleted = await svc.delete_class_map(session, map_id)
    if not deleted:
        raise AppError("lms_not_found", f"Маппинг {map_id} не найден", 404)
    await audit_svc.record(
        session,
        user,
        "lms.class_map.delete",
        target_type="lms_class_map",
        target_id=str(map_id),
        source="api",
        request=request,
    )
    await session.commit()
    return Response(status_code=204)
