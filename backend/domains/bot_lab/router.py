"""Роутер /api/v1/bots (Design §12.2): версии ботов, тест хода, матчи."""

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import func, select

from core.base import CamelModel
from core.config import settings
from core.errors import AppError
from domains.auth.deps import CurrentUser, DbSession, require_role
from domains.auth.models import User, UserRole
from domains.bot_lab import service as svc
from domains.bot_lab.queues import (
    ACTIVE_MATCH_TTL_S,
    MATCH_QUEUES,
    MAX_ACTIVE_MATCHES,
    active_key,
    queue_for_opponent,
    queue_kind,
    refused_key,
)

router = APIRouter(prefix="/bots", tags=["bot_lab"])
admin_router = APIRouter(prefix="/admin", tags=["bot_lab"])

AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]


class BotCreateIn(CamelModel):
    code: str = Field(min_length=10, max_length=20000)
    entry: str = Field(default="choose_move", max_length=64)


class BotOut(CamelModel):
    id: str
    versionNo: int
    entry: str
    isActive: bool
    createdAt: str


class BotTestIn(CamelModel):
    fen: str = Field(min_length=10, max_length=128)


class BotTestOut(CamelModel):
    ok: bool
    moveUci: str | None
    timeMs: int
    error: str | None
    errorType: str | None
    output: str | None


class MatchRunIn(CamelModel):
    opponent: str = Field(
        default="random",
        pattern=r"^(random|greedy|minimax2|stockfish-1400|stockfish-1600|stockfish-1800)$",
    )


class MatchRunOut(CamelModel):
    matchId: int
    status: str


class MatchQueueMetricOut(CamelModel):
    kind: str
    queue: str
    limit: int
    queued: int
    active: int
    refused: int


class MatchMetricsOut(CamelModel):
    hours: int
    total: int
    byOpponent: dict[str, int]
    timeouts: int
    avgDurationMs: int | None
    p95DurationMs: int | None
    refused: int
    queues: list[MatchQueueMetricOut]


class MatchOut(CamelModel):
    id: str
    opponent: str
    result: str
    movesCount: int
    durationMs: int
    eloDelta: float
    startedAt: str
    finishedAt: str | None


class StatsOut(CamelModel):
    elo: float
    wins: int
    losses: int
    draws: int


@router.get("", response_model=list[BotOut])
async def list_bots(user: CurrentUser, session: DbSession) -> list[BotOut]:
    bots = await svc.list_bots(session, user)
    return [
        BotOut(
            id=str(b.id),
            versionNo=b.version_no,
            entry=b.entry,
            isActive=b.is_active,
            createdAt=b.created_at.isoformat(),
        )
        for b in bots
    ]


@router.post("", status_code=201, response_model=BotOut)
async def create_bot(
    body: BotCreateIn, user: CurrentUser, session: DbSession
) -> BotOut:
    bot = await svc.create_bot(session, user, body.code, body.entry)
    return BotOut(
        id=str(bot.id),
        versionNo=bot.version_no,
        entry=bot.entry,
        isActive=bot.is_active,
        createdAt=bot.created_at.isoformat(),
    )


# /stats — объявлен раньше /{bot_id} (иначе перехватывается как bot_id="stats")
@router.get("/stats", response_model=StatsOut)
async def bot_stats(user: CurrentUser, session: DbSession) -> StatsOut:
    from domains.bot_lab.models import BotStats

    stats = await session.get(BotStats, user.id)
    if stats is None:
        return StatsOut(elo=1000.0, wins=0, losses=0, draws=0)
    return StatsOut(
        elo=float(stats.elo), wins=stats.wins, losses=stats.losses, draws=stats.draws
    )


# /leaderboard — тоже раньше /{bot_id} (S-33: иначе 422 как int).
@router.get("/leaderboard")
async def leaderboard(
    user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict]:
    """Лидерборд по Elo (§7.6; v0.1 — открытым списком)."""
    from domains.bot_lab.replay import leaderboard as lb

    return await lb(session, limit)


@router.get("/{bot_id}", response_model=BotOut)
async def get_bot(bot_id: int, user: CurrentUser, session: DbSession) -> BotOut:
    bot = await svc.get_bot(session, user, bot_id)
    return BotOut(
        id=str(bot.id),
        versionNo=bot.version_no,
        entry=bot.entry,
        isActive=bot.is_active,
        createdAt=bot.created_at.isoformat(),
    )


@router.post("/{bot_id}/test", response_model=BotTestOut)
async def test_bot(
    bot_id: int, body: BotTestIn, user: CurrentUser, session: DbSession
) -> BotTestOut:
    result = await svc.test_move(session, user, bot_id, body.fen.strip())
    return BotTestOut(
        ok=result["ok"],
        moveUci=result["moveUci"],
        timeMs=result["timeMs"],
        error=result["error"],
        errorType=result["errorType"],
        output=result["output"] or None,
    )


@router.post("/{bot_id}/match/run", status_code=202, response_model=MatchRunOut)
async def run_match(
    bot_id: int, body: MatchRunIn, user: CurrentUser, session: DbSession, request: Request
) -> MatchRunOut:
    bot = await svc.get_bot(session, user, bot_id)
    from decimal import Decimal

    from arq.connections import RedisSettings, create_pool

    from domains.bot_lab.models import BotMatch, MatchResult

    # S-37: не более 5 активных (pending/running) матчей на пользователя.
    since = datetime.now(UTC) - timedelta(seconds=ACTIVE_MATCH_TTL_S)
    active_count = await session.scalar(
        select(func.count())
        .select_from(BotMatch)
        .where(
            BotMatch.user_id == user.id,
            BotMatch.finished_at.is_(None),
            BotMatch.started_at >= since,
        )
    )
    if (active_count or 0) >= MAX_ACTIVE_MATCHES:
        kind = queue_kind(body.opponent)
        refused = refused_key(kind)
        redis = request.app.state.redis
        await redis.incr(refused)
        await redis.expire(refused, 7 * 24 * 3600)
        raise AppError(
            "match_limit",
            f"Не более {MAX_ACTIVE_MATCHES} одновременных матчей",
            429,
        )

    # S-33: матч создаётся до enqueue, чтобы UI сразу получил matchId и SSE.
    match = BotMatch(
        version_id=bot.id,
        user_id=user.id,
        opponent=body.opponent,
        result=MatchResult.DRAW,
        moves_count=0,
        duration_ms=0,
        elo_delta=Decimal("0"),
    )
    session.add(match)
    await session.flush()
    await session.commit()

    queue = queue_for_opponent(body.opponent)
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job(
            "run_match",
            bot_id,
            body.opponent,
            match.id,
            user.id,
            user.role.value,
            _queue_name=queue,
        )
    finally:
        await pool.aclose()
    return MatchRunOut(matchId=match.id, status="queued")


@router.get("/{bot_id}/matches", response_model=list[MatchOut])
async def bot_matches(
    bot_id: int, user: CurrentUser, session: DbSession
) -> list[MatchOut]:
    from sqlalchemy import select

    from domains.bot_lab.models import BotMatch

    await svc.get_bot(session, user, bot_id)
    rows = (
        await session.execute(
            select(BotMatch)
            .where(BotMatch.version_id == bot_id, BotMatch.user_id == user.id)
            .order_by(BotMatch.id.desc())
            .limit(20)
        )
    ).scalars().all()
    return [
        MatchOut(
            id=str(m.id),
            opponent=m.opponent,
            result=m.result.value,
            movesCount=m.moves_count,
            durationMs=m.duration_ms,
            eloDelta=float(m.elo_delta),
            startedAt=m.started_at.isoformat(),
            finishedAt=m.finished_at.isoformat() if m.finished_at else None,
        )
        for m in rows
    ]


@router.get("/{bot_id}/matches/{match_id}/replay")
async def match_replay(
    bot_id: int, match_id: int, user: CurrentUser, session: DbSession
) -> dict:
    """Реплей матча пошагово (S-20)."""
    from domains.bot_lab.replay import get_replay

    return await get_replay(session, user, bot_id, match_id)


@router.get("/{bot_id}/matches/{match_id}/events", summary="SSE прогресс матча")
async def match_events(
    bot_id: int, match_id: int, user: CurrentUser, session: DbSession, request: Request
) -> StreamingResponse:
    from domains.bot_lab.models import BotMatch
    from domains.bot_lab.replay import match_progress_payload

    await svc.get_bot(session, user, bot_id)
    match = await session.get(BotMatch, match_id)
    if (
        match is None
        or match.version_id != bot_id
        or match.user_id != user.id
    ):
        raise AppError("match_not_found", "Матч не найден", 404)

    initial_ply = match.moves_count
    if match.finished_at is not None:
        done_payload = json.dumps(
            {
                "status": "done",
                "result": match.result.value,
                "eloDelta": float(match.elo_delta),
            }
        )

        async def finished_stream():
            yield f"event: progress\ndata: {done_payload}\n\n"

        return StreamingResponse(finished_stream(), media_type="text/event-stream")

    channel = f"bots:match:{match_id}"

    async def stream():
        pubsub = request.app.state.redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            yield (
                "event: progress\n"
                f"data: {json.dumps({'status': 'running', 'ply': initial_ply})}\n\n"
            )
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=5.0
                )
                if message and message.get("data"):
                    payload = match_progress_payload(message["data"])
                    yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
                    if payload.get("status") in ("done", "failed"):
                        break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream")


@admin_router.get("/matches/metrics", response_model=MatchMetricsOut)
async def match_metrics(
    _guard: AdminOnly,
    session: DbSession,
    request: Request,
    hours: int = Query(default=24, ge=1, le=168),
) -> MatchMetricsOut:
    """S-37: длительность/таймауты/отказы и состояние per-queue воркеров."""
    from domains.bot_lab.models import BotMatch, MatchResult

    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = (
        await session.execute(
            select(BotMatch).where(BotMatch.started_at >= since)
        )
    ).scalars().all()
    durations = sorted(
        row.duration_ms for row in rows if row.finished_at is not None
    )
    p95 = (
        durations[
            min(len(durations) - 1, int(len(durations) * 0.95))
        ]
        if durations
        else None
    )
    by_opponent = Counter(row.opponent for row in rows)
    timeouts = sum(1 for row in rows if row.result == MatchResult.TIMEOUT)

    redis = request.app.state.redis
    queues: list[MatchQueueMetricOut] = []
    refused_total = 0
    for kind, (queue, limit) in MATCH_QUEUES.items():
        queued = int(await redis.zcard(queue) or 0)
        active = int(await redis.scard(active_key(kind)) or 0)
        refused = int(await redis.get(refused_key(kind)) or 0)
        refused_total += refused
        queues.append(
            MatchQueueMetricOut(
                kind=kind,
                queue=queue,
                limit=limit,
                queued=queued,
                active=active,
                refused=refused,
            )
        )

    return MatchMetricsOut(
        hours=hours,
        total=len(rows),
        byOpponent=dict(by_opponent),
        timeouts=timeouts,
        avgDurationMs=(
            int(sum(durations) / len(durations)) if durations else None
        ),
        p95DurationMs=p95,
        refused=refused_total,
        queues=queues,
    )
