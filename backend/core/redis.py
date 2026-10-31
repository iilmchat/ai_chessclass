import redis.asyncio as redis_lib

from core.config import settings

_red_lib = redis_lib


def make_redis() -> "redis_lib.Redis":  # noqa: F821
    """Клиент Redis. Создаётся в lifespan (app.main), хранится в app.state."""
    return _red_lib.from_url(settings.redis_url, decode_responses=True)
