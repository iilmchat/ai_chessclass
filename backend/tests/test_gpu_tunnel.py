"""S-96: GPU tunnel fallback cloud → local (LM Studio) → echo."""

from unittest.mock import AsyncMock

from core.config import settings
from core.db import session_factory
from core.levels import Level
from llm.base import LLMMessage, LLMUnavailableError, LLMUsage
from llm.client import OpenAICompatProvider
from llm.gateway import LLMCallContext, llm_generate


def _msg() -> list[LLMMessage]:
    return [LLMMessage(role="user", content="Назови столицу Франции")]


async def test_cloud_failure_falls_back_to_local(redis_client, monkeypatch):
    """S-96: cloud падает, local LM Studio отвечает — status ok/lmstudio."""
    monkeypatch.setattr(settings, "llm_local_model", "qwen2.5-7b-instruct")
    cloud = AsyncMock(spec=OpenAICompatProvider)
    cloud.generate.side_effect = LLMUnavailableError("routerai down")
    local = AsyncMock(spec=OpenAICompatProvider)
    local.generate.return_value = ("Париж", LLMUsage(10, 3))

    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.comment",
            level=Level.NOVICE,
            messages=_msg(),
            ctx=LLMCallContext(),
            provider=cloud,
            local_provider=local,
        )

    assert result.status == "ok"
    assert result.model_used == "lmstudio"
    assert result.fallback_from == "failover:cloud"
    assert "Париж" in result.text
    assert cloud.generate.await_count == 1
    assert local.generate.await_count == 1
    assert local.generate.await_args.args[0] == "qwen2.5-7b-instruct"


async def test_local_failure_falls_back_to_echo(redis_client):
    """S-96: туннель/local таймаут — echo, fallback_from=failover:local."""
    cloud = AsyncMock(spec=OpenAICompatProvider)
    cloud.generate.side_effect = LLMUnavailableError("routerai down")
    local = AsyncMock(spec=OpenAICompatProvider)
    local.generate.side_effect = TimeoutError("gpu tunnel timeout")

    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.comment",
            level=Level.NOVICE,
            messages=_msg(),
            ctx=LLMCallContext(),
            provider=cloud,
            local_provider=local,
        )

    assert result.status == "echo"
    assert result.model_used == "echo"
    assert result.fallback_from == "failover:local"
    assert cloud.generate.await_count == 1
    assert local.generate.await_count == 1


async def test_breaker_opens_for_local_and_switches_to_echo(redis_client):
    """S-96: 5 ошибок local → cb:state:local=open; 6-й запрос — echo."""
    cloud = AsyncMock(spec=OpenAICompatProvider)
    cloud.generate.side_effect = LLMUnavailableError("routerai down")
    local = AsyncMock(spec=OpenAICompatProvider)
    local.generate.side_effect = TimeoutError("gpu tunnel timeout")

    async with session_factory() as session:
        for _ in range(5):
            result = await llm_generate(
                session,
                redis_client,
                route="python_teacher.comment",
                level=Level.NOVICE,
                messages=_msg(),
                ctx=LLMCallContext(),
                provider=cloud,
                local_provider=local,
            )
            assert result.status == "echo"
            assert result.fallback_from == "failover:local"

        assert await redis_client.get("cb:state:local") == "open"
        assert await redis_client.get("cb:failures:local") == "5"

        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.comment",
            level=Level.NOVICE,
            messages=_msg(),
            ctx=LLMCallContext(),
            provider=cloud,
            local_provider=local,
        )
        assert result.status == "echo"
        assert result.fallback_from == "failover:cb_open"
        assert cloud.generate.await_count == 5
        assert local.generate.await_count == 5
