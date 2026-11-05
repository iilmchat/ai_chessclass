"""Юнит-тесты OpenAI-совместимого клиента (httpx MockTransport, без сети)."""

import httpx
import pytest

from core.config import settings
from llm.base import LLMMessage, LLMUnavailableError, is_placeholder_secret
from llm.client import OpenAICompatProvider


def _ok_response(content: str | None = "Привет! Вот разбор.") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 80},
        },
        request=httpx.Request("POST", "http://llm.test/chat/completions"),
    )


def _provider(handler) -> OpenAICompatProvider:
    transport = httpx.MockTransport(handler)
    return OpenAICompatProvider(
        base_url="http://llm.test/v1", api_key="test-key", transport=transport
    )


async def test_local_provider_uses_local_api_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_local_base_url", "http://local.test/v1")
    monkeypatch.setattr(settings, "llm_local_api_key", "local-secret")

    provider = OpenAICompatProvider(
        base_url="http://local.test/v1",
        transport=httpx.MockTransport(lambda request: _ok_response()),
    )
    assert provider.api_key == "local-secret"
    assert provider._client.headers.get("authorization") == "Bearer local-secret"
    await provider.close()


async def test_generate_success_and_usage():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'"minimax-m3.1"' in body  # слаг передан; формат JSON не проверяем
        assert b"python_teacher" not in body  # домены не просачиваются в транспорт
        return _ok_response()

    provider = _provider(handler)
    text, usage = await provider.generate(
        "minimax-m3.1", [LLMMessage(role="user", content="Проверка")]
    )
    assert text == "Привет! Вот разбор."
    assert usage.prompt_tokens == 120
    assert usage.total_tokens == 200
    await provider.close()


async def test_generate_retry_then_success():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, request=request)
        return _ok_response()

    provider = _provider(handler)
    text, _ = await provider.generate("m1", [LLMMessage(role="user", content="x")])
    assert calls == 2
    assert "разбор" in text
    await provider.close()


async def test_generate_retry_uses_backoff_with_jitter(monkeypatch):
    """S-70: пауза = base_delay * 2^(attempt-1) + random.uniform(0, 0.5)."""
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("llm.client.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("llm.client.random.uniform", lambda _low, _high: 0.25)
    monkeypatch.setattr(settings, "llm_retry_delay_s", 2.0)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, request=request)
        return _ok_response()

    provider = _provider(handler)
    await provider.generate("m1", [LLMMessage(role="user", content="x")])
    assert delays == [pytest.approx(2.25)]
    await provider.close()


async def test_generate_unavailable_after_retry():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    provider = _provider(handler)
    with pytest.raises(LLMUnavailableError):
        await provider.generate("m1", [LLMMessage(role="user", content="x")])
    await provider.close()


async def test_generate_rejects_null_content():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _ok_response(None)

    provider = _provider(handler)
    with pytest.raises(LLMUnavailableError, match="пустой"):
        await provider.generate("m1", [LLMMessage(role="user", content="x")])
    assert calls == 2  # null content не считается успехом, был retry
    await provider.close()


async def test_not_configured_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response()

    provider = OpenAICompatProvider(
        base_url="", api_key="", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(LLMUnavailableError, match="не настроен"):
        await provider.generate("m1", [LLMMessage(role="user", content="x")])
    await provider.close()


async def test_list_models():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(
            200,
            json={"data": [{"id": "m-a"}, {"id": "m-b"}]},
            request=request,
        )

    provider = _provider(handler)
    models = await provider.list_models()
    assert models == ["m-a", "m-b"]
    await provider.close()


def test_placeholder_secret():
    assert is_placeholder_secret("change_me_api_key")
    assert is_placeholder_secret("")
    assert not is_placeholder_secret("sk-real-key-123")
