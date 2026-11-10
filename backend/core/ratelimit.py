"""Redis-утилиты rate-limit и lockout (Design §12.3, §13.1).

S-90: lockout привязан к аккаунту (email), а не к IP. IP остаётся мягким
лимитом, чтобы распределённый перебор не положил БД: 50 неудач/мин → пауза
1 мин. Аккаунт блокируется на 10 мин после 5 неудач/мин.
"""

from redis.asyncio import Redis

from core.errors import AppError

ACCOUNT_FAIL_KEY = "lockout:fail:account:{email}"
ACCOUNT_LOCK_KEY = "lockout:account:{email}"
IP_FAIL_KEY = "lockout:fail:ip:{ip}"
IP_LOCK_KEY = "lockout:ip:{ip}"

AUTH_FAIL_THRESHOLD = 5  # неудачных попыток аккаунта ...
AUTH_FAIL_WINDOW_S = 60  # ... в окне 60 c
AUTH_LOCKOUT_S = 600  # блокировка аккаунта 10 мин

AUTH_IP_FAIL_THRESHOLD = 50  # мягкий лимит неудач с одного IP ...
AUTH_IP_FAIL_WINDOW_S = 60  # ... в окне 60 c
AUTH_IP_LOCKOUT_S = 60  # ... пауза 1 мин


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _account_fail_key(email: str) -> str:
    return ACCOUNT_FAIL_KEY.format(email=_normalize_email(email))


def _account_lock_key(email: str) -> str:
    return ACCOUNT_LOCK_KEY.format(email=_normalize_email(email))


def _ip_fail_key(ip: str) -> str:
    return IP_FAIL_KEY.format(ip=ip)


def _ip_lock_key(ip: str) -> str:
    return IP_LOCK_KEY.format(ip=ip)


async def is_locked_out(redis: Redis, *, email: str, ip: str) -> bool:
    """True, если аккаунт или IP временно заблокированы."""
    if await redis.exists(_account_lock_key(email)):
        return True
    return bool(await redis.exists(_ip_lock_key(ip)))


async def register_auth_failure(redis: Redis, *, email: str, ip: str) -> None:
    """Учесть неудачный логин: 5/мин на аккаунт и 50/мин на IP."""
    account_key = _account_fail_key(email)
    account_count = await redis.incr(account_key)
    if account_count == 1:
        await redis.expire(account_key, AUTH_FAIL_WINDOW_S)
    if account_count >= AUTH_FAIL_THRESHOLD:
        await redis.set(_account_lock_key(email), "1", ex=AUTH_LOCKOUT_S)
        await redis.delete(account_key)

    ip_key = _ip_fail_key(ip)
    ip_count = await redis.incr(ip_key)
    if ip_count == 1:
        await redis.expire(ip_key, AUTH_IP_FAIL_WINDOW_S)
    if ip_count >= AUTH_IP_FAIL_THRESHOLD:
        await redis.set(_ip_lock_key(ip), "1", ex=AUTH_IP_LOCKOUT_S)
        await redis.delete(ip_key)


async def clear_account_failures(redis: Redis, email: str) -> None:
    """Сбросить счётчик неудач после успешного входа (lockout не трогаем)."""
    await redis.delete(_account_fail_key(email))


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
