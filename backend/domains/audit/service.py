"""Журнал аудита (S-41): запись действий и выборка для auditor/учителя."""

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from domains.audit.models import AuditLog
from domains.auth.models import User

EXPORT_LIMIT = 10_000


async def record(
    session: AsyncSession,
    actor: User | None,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | int | None = None,
    source: str = "api",
    meta: dict | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Добавить запись в текущую транзакцию (commit — на уровне запроса)."""
    log = AuditLog(
        actor_id=actor.id if actor is not None else None,
        actor_email=actor.email if actor is not None else None,
        actor_role=actor.role.value if actor is not None else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        source=source,
        meta=meta or {},
        request_id=(
            getattr(request.state, "request_id", None)
            if request is not None
            else None
        ),
    )
    session.add(log)
    await session.flush()
    return log


def _filtered(
    *,
    actor_id: int | None,
    action: str | None,
    target_type: str | None,
    source: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Select:
    stmt = select(AuditLog)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if source:
        stmt = stmt.where(AuditLog.source == source)
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    return stmt


async def list_logs(
    session: AsyncSession,
    *,
    actor_id: int | None = None,
    action: str | None = None,
    target_type: str | None = None,
    source: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditLog], int]:
    conditions = _filtered(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        source=source,
        date_from=date_from,
        date_to=date_to,
    )
    total = int(
        await session.scalar(
            select(func.count()).select_from(conditions.subquery())
        )
        or 0
    )
    rows = (
        await session.execute(
            conditions.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), total


async def export_logs(
    session: AsyncSession,
    *,
    actor_id: int | None = None,
    action: str | None = None,
    target_type: str | None = None,
    source: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[AuditLog]:
    rows = (
        await session.execute(
            _filtered(
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                source=source,
                date_from=date_from,
                date_to=date_to,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(EXPORT_LIMIT)
        )
    ).scalars().all()
    return list(rows)
