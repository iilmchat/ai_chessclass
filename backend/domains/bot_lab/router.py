"""Роутер /api/v1/bots (Design §12.2): версии ботов, тест хода, матчи."""

from fastapi import APIRouter, Request
from pydantic import Field

from core.base import CamelModel
from core.config import settings
from domains.auth.deps import CurrentUser, DbSession
from domains.bot_lab import service as svc

router = APIRouter(prefix="/bots", tags=["bot_lab"])


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
    opponent: str = Field(default="random", pattern=r"^(random|greedy|minimax2)$")


class MatchRunOut(CamelModel):
    matchId: int
    status: str


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
    await svc.get_bot(session, user, bot_id)
    from arq.connections import RedisSettings, create_pool

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("run_match", bot_id, body.opponent)
    finally:
        await pool.aclose()
    return MatchRunOut(matchId=-1, status="queued")


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
