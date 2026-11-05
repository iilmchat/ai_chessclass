"""Единый шлюз (Design §8.1/§8.4): llm_generate(route, level, …) → LLMResult.

Цепочка fallback: cloud RouterAI → local LM Studio (флаг) → echo.
Перед шагом — circuit breaker в Redis: упавший провайдер пропускается,
после 60 с — один HALF_OPEN-probe (S-70). Квота дня (Redis) + graceful
downgrade до L1; каждый вызов → llm_calls (Design §8.5). Домены не знают
моделей — только маршрут и уровень (ADR-004).
"""

import logging
import time
from dataclasses import dataclass

from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

import llm.economy as economy
from core.config import settings
from core.levels import Level
from core.tracing import (
    current_trace_id,
    current_trace_id_optional,
    trace_context,
)
from llm.base import LLMMessage, LLMProvider, LLMUsage
from llm.circuit_breaker import CircuitBreaker
from llm.client import OpenAICompatProvider
from llm.echo import EchoProvider
from llm.models_registry import MODELS
from llm.routes import get_route, resolve_tier
from llm.security import guard_llm_output

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LLMCallContext:
    """Кто и зачем вызывает (для квоты и llm_calls)."""

    user_id: int | None = None
    billing_tier: str = "free"
    task_kind: str = "sync"  # sync | async
    trace_id: str | None = None


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
    fallback_from: str | None  # причина: failover:* | quota_*


@dataclass(frozen=True, slots=True)
class _ProviderStep:
    """Шаг цепочки: провайдер, его model_used и ключ circuit breaker."""

    provider: LLMProvider
    model_used: str
    key: str


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
    """S-73: спан `llm.generate` + trace_id для FinOps-строки."""
    with trace_context(ctx.trace_id or current_trace_id(), span_name="llm.generate"):
        span = trace.get_current_span()
        span.set_attribute("llm.route", route)
        span.set_attribute("llm.level", level.value)
        result = await _llm_generate(
            session,
            redis,
            route=route,
            level=level,
            messages=messages,
            ctx=ctx,
            temperature=temperature,
            max_tokens=max_tokens,
            provider=provider,
            local_provider=local_provider,
        )
        span.set_attribute("llm.model_used", result.model_used)
        span.set_attribute("llm.status", result.status)
        return result


async def _llm_generate(
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
    # S-75: LLM-обработка данных ребёнка/подростка только после consent.
    if ctx.user_id is not None:
        from domains.consent.service import ensure_processing_allowed

        await ensure_processing_allowed(session, ctx.user_id)

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
    chain: list[_ProviderStep] = []
    fallback_reason: str | None = None
    if provider is not None:
        chain.append(_ProviderStep(provider, effective.slug, "cloud"))
        if local_provider is not None:  # тест-инъекция local после облака
            chain.append(_ProviderStep(local_provider, "lmstudio", "local"))
    else:
        cloud = get_cloud_provider()
        if cloud.is_configured():
            chain.append(_ProviderStep(cloud, effective.slug, "cloud"))
        else:
            fallback_reason = "failover:no_config"
        if settings.llm_local_fallback:
            chain.append(_ProviderStep(get_local_provider(), "lmstudio", "local"))
    chain.append(_ProviderStep(EchoProvider(), "echo", "echo"))

    cb = CircuitBreaker(redis)
    started = time.monotonic()
    last_error: Exception | None = None
    for index, step in enumerate(chain):
        if not await cb.is_allowed(step.key):
            fallback_reason = "failover:cb_open"
            logger.warning(
                "llm failover: %s (%s) открыт circuit breaker — пропускаем",
                step.key, effective.slug,
            )
            continue
        try:
            with trace.get_tracer("chessclass.llm").start_as_current_span(
                f"llm.provider.{step.key}"
            ) as provider_span:
                provider_span.set_attribute("llm.model", effective.slug)
                provider_span.set_attribute("llm.provider", step.key)
                text, usage = await step.provider.generate(
                    effective.slug, messages,
                    temperature=temperature, max_tokens=max_tokens,
                )
        except Exception as exc:  # noqa: BLE001 — идём дальше по цепочке
            last_error = exc
            await cb.record_failure(step.key)
            fallback_reason = f"failover:{step.key}"
            logger.warning(
                "llm failover: %s (%s) не ответил: %s — пробуем следующий шаг",
                step.model_used, effective.slug, exc,
            )
            continue

        await cb.record_success(step.key)
        guarded = guard_llm_output(text)
        if guarded.suspicious:
            # Содержимое ответа не логируем: только имена находок (LLM02/LLM06).
            logger.warning(
                "llm output guard: route=%s model=%s findings=%s",
                route, step.model_used, ",".join(guarded.findings),
            )
        text = guarded.text
        latency_ms = int((time.monotonic() - started) * 1000)
        status = (
            economy.STATUS_OK if step.model_used != "echo" else economy.STATUS_ECHO
        )
        fallback_from = None
        if not (index == 0 and status == economy.STATUS_OK):
            fallback_from = fallback_reason
        if effective.tier != spec.tier and status == economy.STATUS_OK:
            fallback_from = f"quota_downgrade:{spec.tier}"
        # Ошибка записи FinOps не должна повторять уже оплаченный LLM-вызов.
        await economy.register_call(
            session, redis,
            user_id=ctx.user_id, route=route, level=level.value,
            model_requested=spec.slug, model_used=step.model_used,
            fallback_from=fallback_from, usage=usage, latency_ms=latency_ms,
            status=status, spec=effective, task_kind=ctx.task_kind,
            trace_id=current_trace_id_optional(),
        )
        return LLMResult(
            route=route, level=level, tier=effective.tier,
            model_requested=spec.slug, model_used=step.model_used,
            text=text, usage=usage, status=status, fallback_from=fallback_from,
        )
    raise RuntimeError(f"llm: цепочка fallback исчерпана: {last_error}")


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
        trace_id=current_trace_id_optional(),
    )
    return LLMResult(
        route=route, level=level, tier="echo", model_requested=model_requested,
        model_used="echo", text=text, usage=usage,
        status=economy.STATUS_ECHO, fallback_from=fallback_from,
    )
