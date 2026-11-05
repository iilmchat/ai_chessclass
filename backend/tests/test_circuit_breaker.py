"""Unit-тесты circuit breaker (S-70): CLOSED → OPEN → HALF_OPEN → CLOSED."""

import time

from llm.circuit_breaker import (
    FAILURE_THRESHOLD,
    STATE_CLOSED,
    STATE_HALF_OPEN,
    STATE_OPEN,
    CircuitBreaker,
    failures_key,
    opened_at_key,
    probe_key,
    state_key,
)


async def _open_old_breaker(redis_client) -> None:
    """OPEN с истёкшим recovery — следующий вызов станет HALF_OPEN-probe."""
    await redis_client.set(state_key("cloud"), STATE_OPEN)
    await redis_client.set(opened_at_key("cloud"), str(time.time() - 61))
    await redis_client.set(failures_key("cloud"), str(FAILURE_THRESHOLD))


async def test_opens_after_threshold_and_blocks(redis_client):
    cb = CircuitBreaker(redis_client)
    for _ in range(FAILURE_THRESHOLD):
        assert await cb.is_allowed("cloud") is True
        await cb.record_failure("cloud")
    assert await redis_client.get(state_key("cloud")) == STATE_OPEN
    assert await redis_client.get(failures_key("cloud")) == str(FAILURE_THRESHOLD)
    assert await cb.is_allowed("cloud") is False


async def test_half_open_allows_single_probe(redis_client):
    await _open_old_breaker(redis_client)
    cb = CircuitBreaker(redis_client)
    assert await cb.is_allowed("cloud") is True
    assert await redis_client.get(state_key("cloud")) == STATE_HALF_OPEN
    assert await redis_client.get(probe_key("cloud")) == "1"
    # Второй конкурентный вызов не должен получить свой probe.
    assert await cb.is_allowed("cloud") is False


async def test_half_open_success_closes_and_resets(redis_client):
    await _open_old_breaker(redis_client)
    cb = CircuitBreaker(redis_client)
    assert await cb.is_allowed("cloud") is True
    await cb.record_success("cloud")
    assert await redis_client.get(state_key("cloud")) == STATE_CLOSED
    assert await redis_client.get(failures_key("cloud")) is None
    assert await redis_client.get(probe_key("cloud")) is None
    assert await redis_client.get(opened_at_key("cloud")) is None


async def test_half_open_failure_reopens(redis_client):
    await _open_old_breaker(redis_client)
    cb = CircuitBreaker(redis_client)
    assert await cb.is_allowed("cloud") is True
    await cb.record_failure("cloud")
    assert await redis_client.get(state_key("cloud")) == STATE_OPEN
    assert await redis_client.get(probe_key("cloud")) is None
    # recovery отсчитывается заново: сразу после сбоя probe запрещён.
    assert await cb.is_allowed("cloud") is False
