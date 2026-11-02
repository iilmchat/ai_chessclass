"""S-46: admin observability/retention API + Prometheus /metrics."""

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
from domains.auth.deps import DbSession, require_role, require_scope
from domains.auth.models import User, UserRole
from domains.observability import service as svc
from domains.retention import service as retention_svc

admin_router = APIRouter(prefix="/admin/observability", tags=["observability"])
metrics_router = APIRouter(tags=["observability"])

AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]
AdminOrAuditor = Annotated[User, Depends(require_scope("observability"))]


class SummaryOut(CamelModel):
    db: bool
    redis: bool
    queues: dict[str, int]
    active_matches: dict[str, int]
    llm_cost_today_rub: float
    llm_tokens_today: int
    voice_chars_today: int
    voice_cost_today_rub: float
    disk_free_gb: float
    retention_last_run: str | None


class AlertOut(CamelModel):
    code: str
    severity: str
    message: str


class CostRowOut(CamelModel):
    user_id: str
    email: str | None
    llm_cost_rub: float
    voice_chars: int
    voice_cost_rub: float
    total_cost_rub: float
    tokens_in: int
    tokens_out: int


class CostsOut(CamelModel):
    days: int
    items: list[CostRowOut]


class RetentionRunIn(CamelModel):
    dry_run: bool = False


class RetentionResultOut(CamelModel):
    policy: str
    cutoff: str
    rows: int
    archived: int
    deleted: int
    archive_path: str | None
    dry_run: bool


class RetentionStatusOut(CamelModel):
    policies: list[dict]
    last_run: dict | None


@admin_router.get("/summary", response_model=SummaryOut)
async def summary(
    _guard: AdminOrAuditor, session: DbSession, request: Request
) -> SummaryOut:
    return SummaryOut(**await svc.summary(session, request.app.state.redis))


@admin_router.get("/alerts", response_model=list[AlertOut])
async def alerts(
    _guard: AdminOrAuditor, session: DbSession, request: Request
) -> list[AlertOut]:
    return [
        AlertOut(**item)
        for item in await svc.alerts(session, request.app.state.redis)
    ]


@admin_router.get("/costs", response_model=CostsOut)
async def costs(
    _guard: AdminOnly,
    session: DbSession,
    days: int = Query(default=30, ge=1, le=365),
) -> CostsOut:
    return CostsOut(
        days=days,
        items=[CostRowOut(**row) for row in await svc.costs(session, days)],
    )


@admin_router.get("/costs.csv")
async def costs_csv(
    request: Request,
    user: AdminOnly,
    session: DbSession,
    days: int = Query(default=30, ge=1, le=365),
) -> Response:
    rows = await svc.costs(session, days)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "user_id",
            "email",
            "llm_cost_rub",
            "voice_chars",
            "voice_cost_rub",
            "total_cost_rub",
            "tokens_in",
            "tokens_out",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["userId"],
                row["email"] or "",
                row["llmCostRub"],
                row["voiceChars"],
                row["voiceCostRub"],
                row["totalCostRub"],
                row["tokensIn"],
                row["tokensOut"],
            ]
        )
    await audit_svc.record(
        session,
        user,
        "observability.costs.export",
        target_type="export",
        source="api",
        meta={"days": days, "rows": len(rows)},
        request=request,
    )
    filename = f"costs-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_router.post("/retention/run", response_model=list[RetentionResultOut])
async def run_retention(
    body: RetentionRunIn,
    user: AdminOnly,
    session: DbSession,
) -> list[RetentionResultOut]:
    results = await retention_svc.run_retention(
        session, dry_run=body.dry_run
    )
    await session.commit()
    return [
        RetentionResultOut(
            policy=item.policy,
            cutoff=item.cutoff,
            rows=item.rows,
            archived=item.archived,
            deleted=item.deleted,
            archive_path=item.archive_path,
            dry_run=item.dry_run,
        )
        for item in results
    ]


@admin_router.get("/retention/status", response_model=RetentionStatusOut)
async def retention_status(
    _guard: AdminOrAuditor, session: DbSession
) -> RetentionStatusOut:
    return RetentionStatusOut(
        policies=await retention_svc.retention_counts(session),
        last_run=await retention_svc.last_run(session),
    )


@metrics_router.get("/metrics")
async def metrics(request: Request, session: DbSession) -> Response:
    if settings.metrics_token:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {settings.metrics_token}":
            raise AppError("metrics_forbidden", "Неверный metrics token", 403)
    text = await svc.metrics_text(session, request.app.state.redis)
    return Response(
        content=text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
