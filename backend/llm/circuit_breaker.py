"""Circuit breaker провайдеров LLM (S-70, Design §8.4).

Состояния живут в Redis, чтобы быть общими для api и worker:
CLOSED → 5 ошибок за 60 с → OPEN → через 60 с → HALF_OPEN (один probe).
Ключи: `cb:state:*`, `cb:failures:*`, `cb:probe:*`; `cb:opened_at:*` хранит
метку открытия, поэтому `cb:state:*` остаётся ровно `"open"`/`"half_open"`.
"""

import logging
import time
from typing import Final

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

STATE_CLOSED: Final = "closed"
STATE_OPEN: Final = "open"
STATE_HALF_OPEN: Final = "half_open"

FAILURE_THRESHOLD: Final = 5
RECOVERY_SECONDS: Final = 60
FAILURE_WINDOW_SECONDS: Final = 60

_VALID_STATES = frozenset({STATE_CLOSED, STATE_OPEN, STATE_HALF_OPEN})


def state_key(provider_key: str) -> str:
    return f"cb:state:{provider_key}"


def failures_key(provider_key: str) -> str:
    return f"cb:failures:{provider_key}"


def probe_key(provider_key: str) -> str:
    return f"cb:probe:{provider_key}"


def opened_at_key(provider_key: str) -> str:
    return f"cb:opened_at:{provider_key}"


def _as_str(value: object) -> str:
    """Redis может вернуть bytes (worker без decode_responses)."""
    if isinstance(value, bytes):
        return value.decode()
    return "" if value is None else str(value)


class CircuitBreaker:
    """Redis-backend circuit breaker: не «долбить» упавший провайдер."""

    def __init__(
        self,
        redis: Redis,
        *,
        threshold: int = FAILURE_THRESHOLD,
        recovery_s: int = RECOVERY_SECONDS,
        window_s: int = FAILURE_WINDOW_SECONDS,
    ) -> None:
        self.redis = redis
        self.threshold = threshold
        self.recovery_s = recovery_s
        self.window_s = window_s

    async def _get_state(self, provider_key: str) -> str:
        raw = await self.redis.get(state_key(provider_key))
        state = _as_str(raw).lower()
        # Неизвестное/битое значение трактуем как CLOSED (fail-open):
        # сбой CB не должен навсегда отключать провайдера.
        return state if state in _VALID_STATES else STATE_CLOSED

    async def _get_opened_at(self, provider_key: str) -> float:
        raw = _as_str(await self.redis.get(opened_at_key(provider_key)))
        try:
            return float(raw) if raw else 0.0
        except ValueError:
            return 0.0

    async def is_allowed(self, provider_key: str) -> bool:
        """Можно ли звать провайдера; в HALF_OPEN — только один probe."""
        state = await self._get_state(provider_key)
        if state == STATE_OPEN:
            elapsed = time.time() - await self._get_opened_at(provider_key)
            if elapsed < self.recovery_s:
                return False
            await self.redis.set(state_key(provider_key), STATE_HALF_OPEN)
            state = STATE_HALF_OPEN
            logger.warning(
                "circuit breaker %s: OPEN → HALF_OPEN после %d с",
                provider_key, self.recovery_s,
            )
        if state == STATE_HALF_OPEN:
            # nx=True защищает от thundering herd: пробу снимает один процесс.
            acquired = await self.redis.set(
                probe_key(provider_key), "1", nx=True, ex=self.recovery_s
            )
            return bool(acquired)
        return True

    async def record_success(self, provider_key: str) -> None:
        """Успех закрывает breaker и сбрасывает окно ошибок."""
        state = await self._get_state(provider_key)
        await self.redis.delete(
            failures_key(provider_key),
            probe_key(provider_key),
            opened_at_key(provider_key),
        )
        await self.redis.set(state_key(provider_key), STATE_CLOSED)
        if state != STATE_CLOSED:
            logger.info("circuit breaker %s: %s → CLOSED", provider_key, state)

    async def record_failure(self, provider_key: str) -> None:
        """Считает ошибку в окне; на пороге (или сбое probe) открывает breaker."""
        state = await self._get_state(provider_key)
        count = int(await self.redis.incr(failures_key(provider_key)))
        if count == 1:
            await self.redis.expire(failures_key(provider_key), self.window_s)
        if state == STATE_HALF_OPEN or count >= self.threshold:
            await self.redis.set(state_key(provider_key), STATE_OPEN)
            await self.redis.set(opened_at_key(provider_key), f"{time.time():.6f}")
            await self.redis.delete(probe_key(provider_key))
            logger.warning(
                "circuit breaker %s: %s → OPEN (failures=%d)",
                provider_key, state, count,
            )
