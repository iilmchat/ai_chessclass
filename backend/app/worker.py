"""arq-воркер (Design §3.2/:151). Очереди analyze/matches/pdf появятся позже (E-04/E-07/E-09)."""

import logging

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


class WorkerSettings:
    functions = [heartbeat, analyze_position, analyze_game]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    # arq default create_pool пишет в "arq:queue"; разделение на analyze/
    # matches/pdf — при росте нагрузок (Design §11.1)
    queue_name = "arq:queue"
    max_jobs = 4
    job_timeout = 300  # BOT_MATCH_BUDGET_S=120 + запас
    health_check_interval = 30
