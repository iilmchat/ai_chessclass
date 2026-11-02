"""S-49: admin API LMS LRS — status, sync, delivery journal/CSV."""

import csv
import io
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from core.base import CamelModel
from domains.audit import service as audit_svc
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole
from domains.lms import service as svc
from domains.lms.models import LrsDelivery

router = APIRouter(prefix="/admin/lms", tags=["lms"])
AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]


class LmsStatusOut(CamelModel):
    configured: bool
    endpoint: str | None
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
    result = await svc.sync(session)
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
