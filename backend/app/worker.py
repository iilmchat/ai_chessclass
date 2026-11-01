"""arq-воркер (Design §3.2/§15.1): analyze/pdf — default queue, matches — per-queue (S-37)."""

import logging
import os

import arq
from arq.connections import RedisSettings

from core.config import settings

logger = logging.getLogger(__name__)


async def heartbeat(ctx: dict) -> str:  # noqa: ARG001 — сигнатура arq
    """Дым-задача: подтверждает живость воркера (S-01)."""
    logger.info("worker heartbeat...")
    return "pong"


async def analyze_position(ctx: dict, fen: str, level: str) -> dict:
    """Анализ позиции через Stockfish (S-11; SF живёт только в воркере)."""
    from engine.service import EngineService

    logger.info("worker: analyze_position %s (%s)", fen, level)
    async with EngineService() as engine:
        lines = await engine.analyze(fen, level, interactive=True)
    return {"facts": [line.model_dump() for line in lines]}


async def analyze_game(ctx: dict, game_id: int) -> dict:
    """Разбор партии: пошаговые eval'ы + blunder-детект (S-12)."""
    from domains.chess_lab import service as chess_svc

    logger.info("worker: analyze_game game_id=%s", game_id)
    return await chess_svc.analyze_game_job(game_id, ctx["redis"])


async def scores_recalc(ctx: dict) -> dict:
    """Nightly: пересчёт недельных EMA по всем пользователям (S-16)."""
    from sqlalchemy import select

    from core.db import session_factory
    from domains.auth.models import User
    from domains.cognitive import service as cognitive_svc

    logger.info("worker: scores_recalc (nightly)")
    async with session_factory() as session:
        user_ids = (
            await session.execute(select(User.id).where(User.is_active.is_(True)))
        ).scalars().all()
    updated = 0
    for user_id in user_ids:
        async with session_factory() as session:
            updated += await cognitive_svc.recalc_user_scores(session, user_id)
            await session.commit()
    return {"users": len(user_ids), "updatedRows": updated}


async def run_match(
    ctx: dict, bot_version_id: int, opponent: str, match_id: int | None = None
) -> dict:
    """Матч бота против оппонента лестницы (S-18; без LLM)."""
    from domains.bot_lab.match import run_match as run
    from domains.bot_lab.queues import ACTIVE_MATCH_TTL_S, active_key, queue_kind

    kind = queue_kind(opponent)
    active = active_key(kind)
    redis = ctx["redis"]
    if match_id is not None:
        await redis.sadd(active, match_id)
        await redis.expire(active, ACTIVE_MATCH_TTL_S)

    logger.info("worker: run_match bot=%s vs %s queue=%s", bot_version_id, opponent, kind)
    try:
        return await run(bot_version_id, opponent, redis, match_id=match_id)
    finally:
        if match_id is not None:
            await redis.srem(active, match_id)


class WorkerSettings:
    functions = [heartbeat, analyze_position, analyze_game, scores_recalc, run_match]
    #: nightly-пересчёт EMA (§10.3) — 03:40 UTC
    cron_jobs = [arq.cron("app.worker.scores_recalc", hour=3, minute=40, run_at_startup=False)]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    #: default queue — analyze/pdf; match workers получают WORKER_QUEUE из compose
    queue_name = os.getenv("WORKER_QUEUE", "arq:queue")
    max_jobs = int(os.getenv("WORKER_MAX_JOBS", "4"))
    job_timeout = 300  # BOT_MATCH_BUDGET_S=120 + запас
    health_check_interval = 30
