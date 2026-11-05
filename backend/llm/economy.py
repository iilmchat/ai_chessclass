"""Экономика шлюза (Design §8.5): запись llm_calls, квоты Redis, usage_daily.

Ключ квоты — `quota:{user}:{date}` (§11.1); бюджеты из config
(free 50k / pro 500k токенов/день). judge — zero-квотный маршрут.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from llm.base import LLMMessage, LLMUsage
from llm.models import LLMCall, UsageDaily
from llm.models_registry import MODELS, ModelSpec

logger = logging.getLogger(__name__)

#: маршруты, не расходующие квоту (Design §8.5: judge — zero-cost;
#: матчи ботов вообще без LLM)
ZERO_QUOTA_ROUTES = frozenset({"anticheat.judge_explain"})

STATUS_OK = "ok"
STATUS_ECHO = "echo"
STATUS_ERROR = "error"


def quota_key(user_id: int, day: date | None = None) -> str:
    day = day or datetime.now(UTC).date()
    return f"quota:{user_id}:{day.isoformat()}"


def daily_budget(billing_tier: str) -> int:
    return (
        settings.budget_pro_tokens_day
        if billing_tier == "pro"
        else settings.budget_free_tokens_day
    )


def estimate_tokens(messages: list[LLMMessage]) -> int:
    """Грубая оценка входных токенов (решение о downgrade; ~4 симв/токен)."""
    return sum(len(m.content) for m in messages) // 4 + 16


def compute_cost(tokens: int, price: Decimal | None) -> Decimal | None:
    """₽ за N токенов по цене ₽/1M; цена не задана → None."""
    if price is None:
        return None
    return (Decimal(tokens) / Decimal(1_000_000) * price).quantize(Decimal("0.0001"))


@dataclass(frozen=True, slots=True)
class QuotaVerdict:
    allowed: bool              # False → сразу echo
    effective_spec: ModelSpec  # тир после возможного downgrade
    used: int
    budget: int


async def check_quota(
    redis,
    user_id: int | None,
    billing_tier: str,
    route: str,
    spec: ModelSpec,
    messages: list[LLMMessage],
) -> QuotaVerdict:
    """Квота дня + graceful downgrade (Design §8.5): тир → L1 → echo."""
    if user_id is None or route in ZERO_QUOTA_ROUTES:
        return QuotaVerdict(True, spec, 0, 0)
    used = int(await redis.get(quota_key(user_id)) or 0)
    budget = daily_budget(billing_tier)
    if used >= budget:
        logger.warning(
            "llm quota: user_id=%s исчерпал бюджет %d/%d — echo", user_id, used, budget
        )
        return QuotaVerdict(False, spec, used, budget)
    if spec.tier != "L1" and used + estimate_tokens(messages) > budget:
        logger.info(
            "llm quota: user_id=%s остаток %d/%d — downgrade %s → L1",
            user_id, used, budget, spec.tier,
        )
        return QuotaVerdict(True, MODELS["L1"], used, budget)
    return QuotaVerdict(True, spec, used, budget)


async def register_call(
    session: AsyncSession,
    redis,
    *,
    user_id: int | None,
    route: str,
    level: str,
    model_requested: str,
    model_used: str,
    fallback_from: str | None,
    usage: LLMUsage,
    latency_ms: int,
    status: str,
    spec: ModelSpec,
    task_kind: str = "sync",
    trace_id: str | None = None,
) -> None:
    """Одна строка llm_calls + (для ok) upsert usage_daily + квота Redis."""
    cost_in = compute_cost(usage.prompt_tokens, spec.price_in)
    cost_out = compute_cost(usage.completion_tokens, spec.price_out)
    session.add(
        LLMCall(
            user_id=user_id,
            route=route,
            level=level,
            model_requested=model_requested,
            model_used=model_used,
            fallback_from=fallback_from,
            tokens_in=usage.prompt_tokens,
            tokens_out=usage.completion_tokens,
            cost_in=cost_in,
            cost_out=cost_out,
            latency_ms=latency_ms,
            status=status,
            task_kind=task_kind,
            trace_id=trace_id,
        )
    )
    if user_id is not None and status == STATUS_OK:
        cost_total = (cost_in or Decimal("0")) + (cost_out or Decimal("0"))
        await _upsert_usage_daily(
            session, user_id, usage.prompt_tokens, usage.completion_tokens, cost_total
        )
        day_total = usage.prompt_tokens + usage.completion_tokens
        if day_total > 0:
            key = quota_key(user_id)
            await redis.incrby(key, day_total)
            if int(await redis.ttl(key) or -1) < 0:
                await redis.expire(key, 48 * 3600)
    await session.flush()


async def _upsert_usage_daily(
    session: AsyncSession, user_id: int, t_in: int, t_out: int, cost: Decimal
) -> None:
    stmt = pg_insert(UsageDaily).values(
        user_id=user_id,
        day=datetime.now(UTC).date(),
        tokens_in=t_in,
        tokens_out=t_out,
        cost_total=cost,
        updated_at=datetime.now(UTC),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "day"],
        set_={
            "tokens_in": UsageDaily.tokens_in + t_in,
            "tokens_out": UsageDaily.tokens_out + t_out,
            "cost_total": UsageDaily.cost_total + cost,
            "updated_at": datetime.now(UTC),
        },
    )
    await session.execute(stmt)


async def finops_daily(session: AsyncSession, days: int) -> list[tuple]:
    """Агрегат FinOps по дням (admin, Design §8.5/§12.2)."""
    stmt = (
        select(
            UsageDaily.day,
            func.count(UsageDaily.user_id),
            func.sum(UsageDaily.tokens_in),
            func.sum(UsageDaily.tokens_out),
            func.sum(UsageDaily.cost_total),
        )
        .group_by(UsageDaily.day)
        .order_by(UsageDaily.day.desc())
        .limit(days)
    )
    return list((await session.execute(stmt)).all())


async def set_quota_for_tests(redis, user_id: int, tokens: int) -> None:
    """Хелпер тестов: выставить счётчик квоты дня."""
    key = quota_key(user_id)
    await redis.set(key, tokens)
    await redis.expire(key, 48 * 3600)
