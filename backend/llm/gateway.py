"""Единый шлюз (Design §8.1/§8.4): llm_generate(route, level, …) → LLMResult.

Цепочка fallback: cloud RouterAI → local LM Studio (флаг) → echo.
Квота дня (Redis) + graceful downgrade до L1; каждый вызов → llm_calls
(Design §8.5). Домены не знают моделей — только маршрут и уровень (ADR-004).
"""

import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

import llm.economy as economy
from core.config import settings
from core.levels import Level
from llm.base import LLMMessage, LLMProvider, LLMUsage
from llm.client import OpenAICompatProvider
from llm.echo import EchoProvider
from llm.models_registry import MODELS
from llm.routes import get_route, resolve_tier

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LLMCallContext:
    """Кто и зачем вызывает (для квоты и llm_calls)."""

    user_id: int | None = None
    billing_tier: str = "free"
    task_kind: str = "sync"  # sync | async


@dataclass(frozen=True, slots=True)
class LLMResult:
    route: str
    level: Level
    tier: str
    model_requested: str  # слаг из реестра
    model_used: str       # фактически обслуживший (cloud slug / lmstudio / echo)
    text: str
    usage: LLMUsage
    status: str           # ok | echo
    fallback_from: str | None  # причина/слаг, после которого переключились


_providers: dict[str, LLMProvider] = {}


def get_cloud_provider() -> OpenAICompatProvider:
    if "cloud" not in _providers:
        _providers["cloud"] = OpenAICompatProvider()
    return _providers["cloud"]  # type: ignore[return-value]


def get_local_provider() -> OpenAICompatProvider:
    if "local" not in _providers:
        _providers["local"] = OpenAICompatProvider(
            base_url=settings.llm_local_base_url, api_key=""
        )
    return _providers["local"]  # type: ignore[return-value]


async def close_llm_providers() -> None:
    for provider in _providers.values():
        await provider.close()
    _providers.clear()


async def llm_generate(
    session: AsyncSession,
    redis,
    *,
    route: str,
    level: Level,
    messages: list[LLMMessage],
    ctx: LLMCallContext,
    temperature: float | None = None,
    max_tokens: int | None = None,
    provider: LLMProvider | None = None,       # для тестов
    local_provider: LLMProvider | None = None,  # для тестов
) -> LLMResult:
    get_route(route)  # валидация маршрута (unknown → AppError)
    spec = MODELS[resolve_tier(route, level)]

    verdict = await economy.check_quota(
        redis, ctx.user_id, ctx.billing_tier, route, spec, messages
    )
    if not verdict.allowed:
        return await _echo(
            session, redis, route=route, level=level, ctx=ctx,
            model_requested=spec.slug, messages=messages,
            fallback_from="quota_exhausted",
        )

    effective = verdict.effective_spec
    chain: list[tuple[LLMProvider, str]] = []  # (provider, marker model_used)
    if provider is not None:
        chain.append((provider, effective.slug))
        if local_provider is not None:  # тест-инъекция local после облака
            chain.append((local_provider, "lmstudio"))
    else:
        cloud = get_cloud_provider()
        if cloud.is_configured():
            chain.append((cloud, effective.slug))
        if settings.llm_local_fallback:
            chain.append((get_local_provider(), "lmstudio"))
    chain.append((EchoProvider(), "echo"))

    started = time.monotonic()
    last_error: Exception | None = None
    for index, (step_provider, model_used) in enumerate(chain):
        try:
            text, usage = await step_provider.generate(
                effective.slug, messages,
                temperature=temperature, max_tokens=max_tokens,
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            status = economy.STATUS_OK if model_used != "echo" else economy.STATUS_ECHO
            fallback_from = None
            if not (index == 0 and status == economy.STATUS_OK):
                fallback_from = _prev_marker(chain, index, effective.slug)
            if effective.tier != spec.tier and status == economy.STATUS_OK:
                fallback_from = f"quota_downgrade:{spec.tier}"
            await economy.register_call(
                session, redis,
                user_id=ctx.user_id, route=route, level=level.value,
                model_requested=spec.slug, model_used=model_used,
                fallback_from=fallback_from, usage=usage, latency_ms=latency_ms,
                status=status, spec=effective, task_kind=ctx.task_kind,
            )
            return LLMResult(
                route=route, level=level, tier=effective.tier,
                model_requested=spec.slug, model_used=model_used,
                text=text, usage=usage, status=status, fallback_from=fallback_from,
            )
        except Exception as exc:  # noqa: BLE001 — идём дальше по цепочке
            last_error = exc
            logger.warning(
                "llm fallback: %s (%s) не ответил: %s — пробуем следующий шаг",
                model_used, effective.slug, exc,
            )
    raise RuntimeError(f"llm: цепочка fallback исчерпана: {last_error}")


def _prev_marker(chain: list[tuple[LLMProvider, str]], index: int, cloud_slug: str) -> str:
    """Причина переключения: слаг облачной модели или маркер предыдущего шага."""
    if index == 0:
        return "cloud_not_configured"
    return chain[index - 1][1] if chain[index - 1][1] != cloud_slug else cloud_slug


async def _echo(
    session: AsyncSession,
    redis,
    *,
    route: str,
    level: Level,
    ctx: LLMCallContext,
    model_requested: str,
    messages: list[LLMMessage],
    fallback_from: str,
) -> LLMResult:
    text, usage = await EchoProvider().generate("echo", messages)
    await economy.register_call(
        session, redis,
        user_id=ctx.user_id, route=route, level=level.value,
        model_requested=model_requested, model_used="echo",
        fallback_from=fallback_from, usage=usage, latency_ms=0,
        status=economy.STATUS_ECHO, spec=MODELS["L1"], task_kind=ctx.task_kind,
    )
    return LLMResult(
        route=route, level=level, tier="echo", model_requested=model_requested,
        model_used="echo", text=text, usage=usage,
        status=economy.STATUS_ECHO, fallback_from=fallback_from,
    )
