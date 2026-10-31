"""arq-воркер (Design §3.2/:151). Очереди analyze/matches/pdf появятся позже (E-04/E-07/E-09)."""

import logging

from arq.connections import RedisSettings

from core.config import settings

logger = logging.getLogger(__name__)


async def heartbeat(ctx: dict) -> str:  # noqa: ARG001 — сигнатура arq
    """Дым-задача: подтверждает живость воркера (S-01)."""
    logger.info("worker heartbeat...")
    return "pong"


class WorkerSettings:
    functions = [heartbeat]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = "default"
    max_jobs = 4
    job_timeout = 300  # BOT_MATCH_BUDGET_S=120 + запас
    health_check_interval = 30
