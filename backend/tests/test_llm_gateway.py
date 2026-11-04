"""Шлюз: generate по маршруту (route→tier→текст), fallback-цепочка (S-05),
circuit breaker (S-70), бутстрап-валидация слагов, admin-эндпоинт моделей."""

import time
from unittest.mock import AsyncMock

import httpx
import pytest
import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from core.levels import Level
from llm.base import LLMMessage, LLMUnavailableError
from llm.bootstrap import validate_model_slags
from llm.client import OpenAICompatProvider
from llm.gateway import LLMCallContext, llm_generate
from llm.models import LLMCall
from tests.conftest import API, login, register_verified


def _mock_provider(handler) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url="http://llm.test/v1",
        api_key="k",
        transport=httpx.MockTransport(handler),
    )


def _chat_ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        request=httpx.Request("POST", "http://llm.test/chat/completions"),
    )


async def test_generate_by_route_intermediate_l2(redis_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert settings.llm_model_l2.encode() in request.read()  # insight intermediate → L2
        return _chat_ok("Позиция спокойная, у белых перевес.")

    provider = _mock_provider(handler)
    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="chess_lab.insight",
            level=Level.INTERMEDIATE,
            messages=[LLMMessage(role="user", content="FEN: rnbqkbnr/...")],
            ctx=LLMCallContext(),
            provider=provider,
        )
        assert "перевес" in result.text
        assert result.tier == "L2"
        assert result.model_requested == settings.llm_model_l2
        assert result.model_used == settings.llm_model_l2
        assert result.status == "ok" and result.fallback_from is None
        # llm_calls: одна строка, статус ok, слаг L2
        row = (
            await session.execute(sa.select(LLMCall).order_by(LLMCall.id.desc()).limit(1))
        ).scalar_one()
        assert row.route == "chess_lab.insight" and row.status == "ok"
        assert row.model_requested == settings.llm_model_l2
        assert row.model_used == settings.llm_model_l2


async def test_advanced_route_uses_l3(redis_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert settings.llm_model_l3.encode() in request.read()  # insight advanced → L3
        return _chat_ok("Глубокий разбор.")

    provider = _mock_provider(handler)
    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="chess_lab.insight",
            level=Level.ADVANCED,
            messages=[LLMMessage(role="user", content="FEN")],
            ctx=LLMCallContext(),
            provider=provider,
        )
        assert result.tier == "L3" and "разбор" in result.text


async def test_fallback_to_echo_when_cloud_fails(redis_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)  # retry тоже 500

    provider = _mock_provider(handler)
    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.comment",
            level=Level.NOVICE,
            messages=[LLMMessage(role="user", content="Проверь код")],
            ctx=LLMCallContext(),
            provider=provider,
        )
        assert result.status == "echo" and result.model_used == "echo"
        assert result.fallback_from == "failover:cloud"
        assert "[echo]" in result.text
        row = (
            await session.execute(sa.select(LLMCall).order_by(LLMCall.id.desc()).limit(1))
        ).scalar_one()
        assert row.status == "echo" and row.model_used == "echo"
        assert row.fallback_from == "failover:cloud"


async def test_echo_when_cloud_not_configured(redis_client):
    # settings.llm_base_url пуст (контейнер) → цепочка сразу echo
    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.comment",
            level=Level.NOVICE,
            messages=[LLMMessage(role="user", content="x")],
            ctx=LLMCallContext(),
        )
        assert result.status == "echo"
        assert result.fallback_from == "failover:no_config"


async def test_db_error_does_not_repeat_paid_llm_call(redis_client, monkeypatch):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _chat_ok("ответ")

    provider = _mock_provider(handler)

    async def fail_register(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("llm.gateway.economy.register_call", fail_register)
    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="db down"):
            await llm_generate(
                session,
                redis_client,
                route="python_teacher.comment",
                level=Level.NOVICE,
                messages=[LLMMessage(role="user", content="x")],
                ctx=LLMCallContext(),
                provider=provider,
            )
    assert calls == 1  # FinOps-сбой не должен повторять оплаченный вызов


async def test_circuit_breaker_opens_after_five_cloud_failures(redis_client):
    """S-70: 5 падений cloud → OPEN; 6-й вызов идёт в echo без облака."""
    cloud = AsyncMock(spec=OpenAICompatProvider)
    cloud.generate.side_effect = LLMUnavailableError("routerai down")
    async with session_factory() as session:
        for _ in range(5):
            result = await llm_generate(
                session,
                redis_client,
                route="python_teacher.comment",
                level=Level.NOVICE,
                messages=[LLMMessage(role="user", content="Проверь код")],
                ctx=LLMCallContext(),
                provider=cloud,
            )
            assert result.status == "echo"
            assert result.fallback_from == "failover:cloud"
        assert await redis_client.get("cb:state:cloud") == "open"
        assert await redis_client.get("cb:failures:cloud") == "5"
        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.comment",
            level=Level.NOVICE,
            messages=[LLMMessage(role="user", content="Проверь код")],
            ctx=LLMCallContext(),
            provider=cloud,
        )
        assert result.status == "echo"
        assert result.fallback_from == "failover:cb_open"
    assert cloud.generate.await_count == 5


async def test_half_open_success_closes_and_resets_failures(redis_client):
    """S-70: после recovery успешный probe закрывает breaker и чистит счётчик."""
    await redis_client.set("cb:state:cloud", "open")
    await redis_client.set("cb:opened_at:cloud", str(time.time() - 61))
    await redis_client.set("cb:failures:cloud", "5")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _chat_ok("Восстановились.")

    provider = _mock_provider(handler)
    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.comment",
            level=Level.NOVICE,
            messages=[LLMMessage(role="user", content="Проверь код")],
            ctx=LLMCallContext(),
            provider=provider,
        )
    assert calls == 1
    assert result.status == "ok"
    assert result.fallback_from is None
    assert await redis_client.get("cb:state:cloud") == "closed"
    assert await redis_client.get("cb:failures:cloud") is None
    assert await redis_client.get("cb:probe:cloud") is None
    assert await redis_client.get("cb:opened_at:cloud") is None


async def test_bootstrap_slags_validation():
    known = {settings.llm_model_l1, settings.llm_model_l2}  # L3/judge — нет у провайдера

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(
            200, json={"data": [{"id": m} for m in sorted(known)]}, request=request
        )

    provider = _mock_provider(handler)
    result = await validate_model_slags(provider)
    assert result["L1"] is True and result["L2"] is True
    assert result["L3"] is False  # нет у провайдера → warning + автопропуск (R-01)
    assert result["judge"] is False


async def test_admin_models_endpoint(admin_client, make_client, unique_email):
    _ = admin_client  # seeds + admin bearer уже в заголовках клиента
    client = await make_client()
    registered = await register_verified(client, unique_email)
    _c, student_access, _uid = await login(client, unique_email)

    response = await admin_client.get(f"{API}/admin/models")
    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "RUB"
    tiers = {m["tier"] for m in body["models"]}
    assert tiers == {"L1", "L2", "L3", "L3_alt", "judge"}
    assert body["models"][0]["priceIn"] == f"{settings.llm_cost_l1_in:.4f}"

    response = await client.get(
        f"{API}/admin/models", headers={"Authorization": f"Bearer {student_access}"}
    )
    assert response.status_code == 403
    _ = registered
