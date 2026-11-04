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


async def retention_run(ctx: dict) -> dict:
    """Nightly: архивировать/удалить устаревшие журналы и кэш (S-46)."""
    from core.db import session_factory
    from domains.retention import service as retention_svc

    logger.info("worker: retention_run (nightly)")
    async with session_factory() as session:
        results = await retention_svc.run_retention(session)
        await session.commit()
    return {
        "policies": {
            item.policy: {"rows": item.rows, "deleted": item.deleted}
            for item in results
        }
    }


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


async def run_tournament_job(ctx: dict, tournament_id: int) -> dict:
    """Async-турнир: bracket/round-robin, replay, восстановление (S-48)."""
    from domains.tournaments.service import run_tournament_job as run

    logger.info("worker: tournament %s", tournament_id)
    tournament = await run(tournament_id, ctx["redis"])
    return {"tournamentId": tournament.id, "status": tournament.status}


async def resume_tournaments(ctx: dict) -> dict:
    """Cron/startup: подхватить queued/running турниры после рестарта."""
    from domains.tournaments.service import resume_tournaments as resume

    count = await resume(ctx["redis"])
    logger.info("worker: resume_tournaments enqueued=%s", count)
    return {"enqueued": count}


async def lms_sync(ctx: dict) -> dict:
    """Cron: xAPI statements → LRS (идемпотентно, retry)."""
    from core.db import session_factory
    from domains.lms import service as lms_svc

    logger.info("worker: lms_sync")
    async with session_factory() as session:
        result = await lms_svc.sync(session)
        await session.commit()
    return result


async def telegram_deliver(ctx: dict) -> dict:
    """Cron: доставка Telegram outbox с retry."""
    from core.db import session_factory
    from domains.telegram import service as telegram_svc

    logger.info("worker: telegram_deliver")
    async with session_factory() as session:
        result = await telegram_svc.deliver_pending(session)
        await session.commit()
    return result


async def telegram_poll(ctx: dict) -> dict:
    """Cron (S-68): long-poll fallback getUpdates (webhook выключен)."""
    from core.db import session_factory
    from domains.telegram import service as telegram_svc

    async with session_factory() as session:
        result = await telegram_svc.poll_updates_once(session, ctx["redis"])
        await session.commit()
    if result.get("processed"):
        logger.info("worker: telegram_poll processed=%s", result["processed"])
    return result


class WorkerSettings:
    functions = [
        heartbeat,
        analyze_position,
        analyze_game,
        scores_recalc,
        retention_run,
        run_match,
        run_tournament_job,
        resume_tournaments,
        lms_sync,
        telegram_deliver,
        telegram_poll,
    ]
    #: nightly-пересчёт EMA (§10.3) — 03:40 UTC; retention — 04:10 UTC
    cron_jobs = [
        arq.cron("app.worker.scores_recalc", hour=3, minute=40, run_at_startup=False),
        arq.cron("app.worker.retention_run", hour=4, minute=10, run_at_startup=False),
        arq.cron("app.worker.resume_tournaments", minute=5, run_at_startup=True),
        arq.cron("app.worker.lms_sync", minute=15, run_at_startup=True),
        arq.cron("app.worker.telegram_deliver", minute=2, run_at_startup=True),
        # S-68: долгая опроска каждые 2 мин (режим без webhook)
        arq.cron("app.worker.telegram_poll", minute=0, second=25, run_at_startup=True),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    #: default queue — analyze/pdf; match workers получают WORKER_QUEUE из compose
    queue_name = os.getenv("WORKER_QUEUE", "arq:queue")
    max_jobs = int(os.getenv("WORKER_MAX_JOBS", "4"))
    job_timeout = 300  # BOT_MATCH_BUDGET_S=120 + запас
    health_check_interval = 30
