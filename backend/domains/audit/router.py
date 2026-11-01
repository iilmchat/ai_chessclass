"""Роутер /admin/audit (S-41): журнал, фильтры, CSV.

Чтение: teacher/admin/auditor. Запись в журнал — только сервисами
(нет публичного POST); auditor не может менять данные.
"""

import csv
import io
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from core.base import CamelModel
from domains.audit import service as audit_svc
from domains.audit.models import AuditLog
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole

router = APIRouter(prefix="/admin/audit", tags=["audit"])

ReadRoles = Annotated[
    User,
    Depends(require_role(UserRole.TEACHER, UserRole.ADMIN, UserRole.AUDITOR)),
]


class AuditLogOut(CamelModel):
    id: str
    actor_id: str | None
    actor_email: str | None
    actor_role: str | None
    action: str
    target_type: str | None
    target_id: str | None
    source: str
    meta: dict
    request_id: str | None
    created_at: datetime


class AuditPageOut(CamelModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int


def _out(log: AuditLog) -> AuditLogOut:
    return AuditLogOut(
        id=str(log.id),
        actor_id=str(log.actor_id) if log.actor_id is not None else None,
        actor_email=log.actor_email,
        actor_role=log.actor_role,
        action=log.action,
        target_type=log.target_type,
        target_id=log.target_id,
        source=log.source,
        meta=log.meta,
        request_id=log.request_id,
        created_at=log.created_at,
    )


@router.get("/logs", response_model=AuditPageOut)
async def list_logs(
    _guard: ReadRoles,
    session: DbSession,
    actor_id: int | None = Query(default=None, alias="actorId"),
    action: str | None = Query(default=None, max_length=64),
    target_type: str | None = Query(default=None, alias="targetType", max_length=32),
    source: str | None = Query(default=None, max_length=32),
    date_from: datetime | None = Query(default=None, alias="dateFrom"),
    date_to: datetime | None = Query(default=None, alias="dateTo"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
) -> AuditPageOut:
    rows, total = await audit_svc.list_logs(
        session,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        source=source,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return AuditPageOut(
        items=[_out(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/export.csv")
async def export_csv(
    request: Request,
    user: ReadRoles,
    session: DbSession,
    actor_id: int | None = Query(default=None, alias="actorId"),
    action: str | None = Query(default=None, max_length=64),
    target_type: str | None = Query(default=None, alias="targetType", max_length=32),
    source: str | None = Query(default=None, max_length=32),
    date_from: datetime | None = Query(default=None, alias="dateFrom"),
    date_to: datetime | None = Query(default=None, alias="dateTo"),
) -> Response:
    rows = await audit_svc.export_logs(
        session,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        source=source,
        date_from=date_from,
        date_to=date_to,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "created_at",
            "actor_id",
            "actor_email",
            "actor_role",
            "action",
            "target_type",
            "target_id",
            "source",
            "request_id",
            "meta",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat(),
                row.actor_id or "",
                row.actor_email or "",
                row.actor_role or "",
                row.action,
                row.target_type or "",
                row.target_id or "",
                row.source,
                row.request_id or "",
                json.dumps(row.meta, ensure_ascii=False, separators=(",", ":")),
            ]
        )

    await audit_svc.record(
        session,
        user,
        "audit.export",
        target_type="audit_logs",
        source="api",
        meta={
            "rows": len(rows),
            "filters": {
                "actorId": actor_id,
                "action": action,
                "targetType": target_type,
                "source": source,
            },
        },
        request=request,
    )
    filename = f"audit-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
