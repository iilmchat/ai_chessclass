"""S-49: xAPI-коннектор LRS с идемпотентной очередью и retry."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from domains.auth.models import User, UserRole
from domains.bot_lab.models import BotStats
from domains.cognitive import service as cognitive_svc
from domains.lms.models import LrsDelivery
from domains.profile.models import UserProfile

logger = logging.getLogger(__name__)

STATUSES = ("pending", "sent", "failed")
SenderFn = Callable[[dict], Awaitable[int]]


def _statement_id(actor_mbox: str, object_id: str, day: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{actor_mbox}|{object_id}|{day}",
        )
    )


async def build_statements(session: AsyncSession) -> list[dict]:
    """Собрать xAPI statements по всем ученикам (идемпотентно за день)."""
    rows = (
        await session.execute(
            select(User, UserProfile)
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .where(User.role == UserRole.STUDENT)
            .order_by(User.id)
        )
    ).all()
    stats = {
        s.user_id: s for s in (await session.execute(select(BotStats))).scalars()
    }
    day = datetime.now(UTC).date().isoformat()
    now = datetime.now(UTC).isoformat()
    statements: list[dict] = []
    for user, profile in rows:
        actor = {
            "mbox": f"mailto:{user.email}",
            "name": (
                profile.display_name
                if profile is not None and profile.display_name
                else user.email
            ),
        }
        for skill in await cognitive_svc.scores_snapshot(session, user.id):
            object_id = f"https://chessclass.local/skills/{skill['slug']}"
            statements.append(
                {
                    "id": _statement_id(actor["mbox"], object_id, day),
                    "actor": actor,
                    "verb": {
                        "id": "http://adlnet.gov/expapi/verbs/experienced",
                        "display": {"ru-RU": "изучил"},
                    },
                    "object": {
                        "id": object_id,
                        "definition": {
                            "name": {"ru-RU": skill["titleRu"]},
                            "type": "https://chessclass.local/activity/skill",
                        },
                    },
                    "result": {
                        "score": {"scaled": round(float(skill["score"]) / 100, 4)},
                        "completion": True,
                    },
                    "timestamp": now,
                }
            )
        stat = stats.get(user.id)
        if stat is not None:
            object_id = f"https://chessclass.local/bots/{user.id}"
            statements.append(
                {
                    "id": _statement_id(actor["mbox"], object_id, day),
                    "actor": actor,
                    "verb": {
                        "id": "http://adlnet.gov/expapi/verbs/achieved",
                        "display": {"ru-RU": "достиг"},
                    },
                    "object": {
                        "id": object_id,
                        "definition": {
                            "name": {"ru-RU": "Рейтинг бота"},
                            "type": "https://chessclass.local/activity/bot-elo",
                        },
                    },
                    "result": {
                        "score": {
                            "raw": float(stat.elo),
                            "min": 0,
                            "max": 3000,
                        },
                        "completion": True,
                    },
                    "timestamp": now,
                }
            )
    return statements


async def enqueue_statements(session: AsyncSession) -> int:
    statements = await build_statements(session)
    if not statements:
        return 0
    existing = set(
        (
            await session.execute(
                select(LrsDelivery.statement_id).where(
                    LrsDelivery.statement_id.in_(
                        [statement["id"] for statement in statements]
                    )
                )
            )
        ).scalars()
    )
    new = [statement for statement in statements if statement["id"] not in existing]
    if new:
        await session.execute(
            pg_insert(LrsDelivery).values(
                [
                    {
                        "statement_id": statement["id"],
                        "payload": statement,
                        "status": "pending",
                        "attempts": 0,
                        "next_attempt_at": datetime.now(UTC),
                    }
                    for statement in new
                ]
            )
        )
        await session.flush()
    return len(new)


async def _send(payload: dict) -> int:
    if not settings.lrs_enabled or not settings.lrs_endpoint:
        raise RuntimeError("LRS не настроен")
    url = f"{settings.lrs_endpoint.rstrip('/')}/statements"
    from core.egress import hostname_of, make_egress_hook

    async with httpx.AsyncClient(
        timeout=settings.lrs_timeout_s,
        event_hooks={
            # S-61: egress allowlist (lrs_endpoint разрешён как настроенный)
            "request": [make_egress_hook(hostname_of(settings.lrs_endpoint) or "")]
        },
    ) as client:
        response = await client.put(
            url,
            params={"statementId": payload["id"]},
            json=payload,
            auth=(settings.lrs_key, settings.lrs_secret),
        )
    return response.status_code


async def deliver_pending(
    session: AsyncSession,
    *,
    sender: SenderFn | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    if sender is None and not settings.lrs_enabled:
        return {"sent": 0, "failed": 0, "pending": 0, "disabled": 1}
    fetch = sender or _send
    now = datetime.now(UTC)
    rows = list(
        (
            await session.execute(
                select(LrsDelivery)
                .where(
                    LrsDelivery.status.in_(("pending", "failed")),
                    LrsDelivery.next_attempt_at <= now,
                )
                .order_by(LrsDelivery.id)
                .limit(limit or settings.lms_sync_batch)
            )
        ).scalars()
    )
    sent = failed = 0
    for row in rows:
        row.attempts += 1
        try:
            status = await fetch(row.payload)
            row.response_status = int(status)
            if 200 <= status < 300:
                row.status = "sent"
                row.sent_at = datetime.now(UTC)
                row.last_error = None
                sent += 1
            else:
                row.status = "failed"
                row.last_error = f"HTTP {status}"
                row.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(3600, 2 ** min(row.attempts, 10))
                )
                failed += 1
        except Exception as exc:  # noqa: BLE001 - retry позже
            row.status = "failed"
            row.last_error = str(exc)[:1000]
            row.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=min(3600, 2 ** min(row.attempts, 10))
            )
            failed += 1
            logger.warning("lms: delivery %s failed: %s", row.id, exc)
    await session.flush()
    pending = int(
        await session.scalar(
            select(func.count())
            .select_from(LrsDelivery)
            .where(LrsDelivery.status == "pending")
        )
        or 0
    )
    return {"sent": sent, "failed": failed, "pending": pending, "disabled": 0}


async def status(session: AsyncSession) -> dict:
    counts = {
        status_name: int(count)
        for status_name, count in (
            await session.execute(
                select(LrsDelivery.status, func.count()).group_by(
                    LrsDelivery.status
                )
            )
        ).all()
    }
    last = (
        await session.execute(
            select(LrsDelivery).order_by(LrsDelivery.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return {
        "configured": bool(settings.lrs_enabled and settings.lrs_endpoint),
        "endpoint": settings.lrs_endpoint or None,
        "counts": {name: counts.get(name, 0) for name in STATUSES},
        "lastDelivery": (
            {
                "id": str(last.id),
                "status": last.status,
                "attempts": last.attempts,
                "responseStatus": last.response_status,
                "sentAt": last.sent_at,
            }
            if last is not None
            else None
        ),
    }


async def list_deliveries(
    session: AsyncSession, *, status_filter: str | None = None, limit: int = 100
) -> list[LrsDelivery]:
    stmt = select(LrsDelivery)
    if status_filter:
        stmt = stmt.where(LrsDelivery.status == status_filter)
    stmt = stmt.order_by(LrsDelivery.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def sync(session: AsyncSession, *, sender: SenderFn | None = None) -> dict:
    queued = await enqueue_statements(session)
    result = await deliver_pending(session, sender=sender)
    return {"queued": queued, **result}
