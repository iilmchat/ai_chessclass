"""S-61: egress allowlist — guard блокирует хосты вне политики.

Проверки: loopback всегда разрешён; неизвестный хост → AppError 502
`egress_blocked`; записи allowlist (host / `*.host` / поддомены);
настроенные базовые URL провайдеров разрешены; OpenAICompatProvider
работает через свой base_url, но вызов на чужой хост тем же клиентом
блокируется (bypass-тест). Паттерны изолируются monkeypatch'ем settings.
"""

import httpx
import pytest

from core.config import settings
from core.egress import (
    ensure_egress_allowed,
    host_allowed,
    hostname_of,
    make_egress_hook,
)
from core.errors import AppError


@pytest.fixture(autouse=True)
def isolated_egress(monkeypatch):
    """Чистая политика: пустой allowlist, пустые базовые URL провайдеров."""
    monkeypatch.setattr(settings, "allowed_egress_hosts", [])
    monkeypatch.setattr(settings, "llm_base_url", "")
    monkeypatch.setattr(settings, "llm_local_base_url", "")
    monkeypatch.setattr(settings, "voice_base_url", "")
    monkeypatch.setattr(settings, "telegram_api_base", "")
    monkeypatch.setattr(settings, "lrs_endpoint", "")


def test_loopback_always_allowed():
    for url in ("http://127.0.0.1:1234/v1", "https://localhost:8080/api"):
        ensure_egress_allowed(url)  # не падает


def test_unknown_host_blocked():
    with pytest.raises(AppError) as exc_info:
        ensure_egress_allowed("https://evil.example/steal")
    assert exc_info.value.code == "egress_blocked"
    assert exc_info.value.status_code == 502
    assert "evil.example" in exc_info.value.detail


def test_allowlist_entry_allows_host_and_subdomains(monkeypatch):
    monkeypatch.setattr(settings, "allowed_egress_hosts", ["routerai.test"])
    assert host_allowed("routerai.test", ["routerai.test"])
    assert host_allowed("api.routerai.test", ["routerai.test"])
    ensure_egress_allowed("https://api.routerai.test/v1")  # ok
    assert not host_allowed("google.ru", ["routerai.test"])


def test_wildcard_pattern_allows_only_subdomains(monkeypatch):
    monkeypatch.setattr(settings, "allowed_egress_hosts", ["*.routerai.test"])
    assert host_allowed("api.routerai.test", ["*.routerai.test"])
    assert not host_allowed("routerai.test", ["*.routerai.test"])
    assert not host_allowed("evil.routerai.evil", ["*.routerai.test"])


def test_configured_provider_bases_allowed(monkeypatch):
    monkeypatch.setattr(settings, "voice_base_url", "https://voice.test")
    monkeypatch.setattr(settings, "lrs_endpoint", "https://lrs.cloud.test/xapi")
    ensure_egress_allowed("https://voice.test/v1/tts")  # настроен — ok
    ensure_egress_allowed("https://lrs.cloud.test/xapi/statements")  # ok
    with pytest.raises(AppError):
        ensure_egress_allowed("https://unrelated.test/x")


def _chat_response(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        },
    )


async def test_llm_provider_guard_blocks_foreign_call():
    from llm.client import OpenAICompatProvider

    provider = OpenAICompatProvider(
        base_url="https://llm.test/v1", transport=httpx.MockTransport(_chat_response)
    )
    # обычный путь: свой base_url разрешён (extra-паттерн клиента)
    text, usage = await provider.generate("some/model", [], temperature=0.1)
    assert text == "ok"
    assert usage.completion_tokens == 2

    # bypass-тест: тем же клиентом на чужой хост — блокируется до транспорта
    calls: list[httpx.Request] = []

    async def handler_unused(request: httpx.Request) -> httpx.Response:  # noqa: RUF029
        calls.append(request)
        return httpx.Response(200)

    blocked_client = httpx.AsyncClient(
        base_url="https://llm.test/v1",
        transport=httpx.MockTransport(handler_unused),
        event_hooks={
            "request": [make_egress_hook(hostname_of("https://llm.test/v1") or "")]
        },
    )
    try:
        with pytest.raises(AppError) as exc_info:
            await blocked_client.post("https://evil.example/steal")
        assert exc_info.value.code == "egress_blocked"
        assert calls == []  # запрос не дошёл до транспорта
    finally:
        await blocked_client.aclose()
        await provider._client.aclose()  # noqa: SLF001 — тестовый доступ


def test_hook_rejects_url_without_host():
    hook = make_egress_hook()
    assert callable(hook)
    with pytest.raises(AppError):
        ensure_egress_allowed("not-a-url")  # hostname пустой → блок


def test_hostname_of_ignores_empty():
    assert hostname_of("") is None
    assert hostname_of("https://api.routerai.test:8443/v1") == "api.routerai.test"
