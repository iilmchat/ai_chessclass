"""E2E шлюза (DoD S-04): generate по маршруту возвращает текст; уровень
выбирает тир; бутстрап-валидация слагов по /models провайдера (R-01)."""

import httpx
import pytest
from conftest import API, login, register_verified

from core.levels import Level
from llm.base import LLMMessage, LLMUnavailableError
from llm.bootstrap import validate_model_slags
from llm.client import OpenAICompatProvider
from llm.gateway import LLMGateway


def _mock_provider(handler) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url="http://llm.test/v1", api_key="k", transport=httpx.MockTransport(handler)
    )


def _chat_ok(model: str, content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        request=httpx.Request("POST", "http://llm.test/chat/completions"),
    )


async def test_gateway_generate_by_route(monkeypatch):
    seen_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'"deepseek-v4.1"' in body  # insight intermediate → L2
        seen_models.append("L2")
        return _chat_ok("deepseek-v4.1", "Позиция спокойная, у белых перевес.")

    gateway = LLMGateway(_mock_provider(handler))
    result = await gateway.generate(
        "chess_lab.insight",
        Level.INTERMEDIATE,
        [LLMMessage(role="user", content="FEN: rnbqkbnr/...")],
        temperature=0.4,
        max_tokens=500,
    )
    assert "перевес" in result.text
    assert result.tier == "L2"
    assert result.model_requested == "deepseek-v4.1"
    assert result.usage.total_tokens == 15


async def test_gateway_advanced_route_l3():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'"beam-1.0-501b"' in body  # insight advanced → L3
        return _chat_ok("beam-1.0-501b", "Глубокий разбор.")

    gateway = LLMGateway(_mock_provider(handler))
    result = await gateway.generate(
        "chess_lab.insight",
        Level.ADVANCED,
        [LLMMessage(role="user", content="FEN")],
    )
    assert result.tier == "L3" and "разбор" in result.text


async def test_gateway_unavailable_when_not_configured():
    gateway = LLMGateway(OpenAICompatProvider(base_url="", api_key=""))
    with pytest.raises(LLMUnavailableError):
        await gateway.generate(
            "python_teacher.comment", Level.NOVICE, [LLMMessage(role="user", content="x")]
        )


async def test_bootstrap_slags_validation():
    known = {"minimax-m3.1", "deepseek-v4.1"}  # L3/judge слаги не заданы в env → skip

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

    # admin видит реестр
    response = await admin_client.get(f"{API}/admin/models")
    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "RUB"
    tiers = {m["tier"] for m in body["models"]}
    assert tiers == {"L1", "L2", "L3", "L3_alt", "judge"}
    assert body["models"][0]["priceIn"] == "7.0000"

    # student → 403 (Design §12.2: модели/цены — admin readonly)
    response = await client.get(
        f"{API}/admin/models", headers={"Authorization": f"Bearer {student_access}"}
    )
    assert response.status_code == 403
    _ = registered
