"""Redis-утилиты rate-limit и lockout (Design §12.3, §13.1)."""

from redis.asyncio import Redis

from core.errors import AppError

FAIL_KEY = "auth:fail:{ip}"
LOCK_KEY = "auth:lock:{ip}"

AUTH_FAIL_THRESHOLD = 5  # неудачных попыток ...
AUTH_FAIL_WINDOW_S = 60  # ... в окне 60 c
AUTH_LOCKOUT_S = 600  # блокировка 10 мин


def _fail_key(ip: str) -> str:
    return FAIL_KEY.format(ip=ip)


def _lock_key(ip: str) -> str:
    return LOCK_KEY.format(ip=ip)


async def is_locked_out(redis: Redis, ip: str) -> bool:
    """IP заблокирован после серии неудачных логинов."""
    return bool(await redis.exists(_lock_key(ip)))


async def register_auth_failure(redis: Redis, ip: str) -> None:
    """Учёт неудачной попытки; на 5-й в минуту — lockout на 10 минут."""
    key = _fail_key(ip)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, AUTH_FAIL_WINDOW_S)
    if count >= AUTH_FAIL_THRESHOLD:
        await redis.set(_lock_key(ip), "1", ex=AUTH_LOCKOUT_S)
        await redis.delete(key)


async def enforce_rate_limit(
    redis: Redis, bucket: str, limit: int, window_s: int
) -> None:
    """Fixed-window счётчик по бакету (например `register:{ip}`).

    При превышении — AppError `rate_limited` (429, RFC 7807).
    """
    key = f"rl:{bucket}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_s)
    if count > limit:
        raise AppError(
            "rate_limited",
            f"Слишком много запросов (лимит {limit} за {window_s} c)",
            429,
        )
