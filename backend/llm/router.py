"""API /api/v1/admin/models (Design §12.2): модели/цены readonly для admin."""

import asyncio
import logging
import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from core.base import CamelModel
from core.config import settings
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole
from llm import economy
from llm.client import OpenAICompatProvider
from llm.gateway import get_cloud_provider
from llm.models import LLMCall
from llm.models_registry import MODELS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["llm"])

AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]


class ModelOut(CamelModel):
    tier: str
    slug: str
    display: str
    role: str
    configured: bool
    priceIn: str | None  # ₽/1M — Numeric(12,4), JSON — строка (JS-safe)
    priceOut: str | None


class ModelsOut(CamelModel):
    providerConfigured: bool
    currency: str
    models: list[ModelOut]


@router.get("/models", summary="Реестр моделей шлюза и цены (Design §8.3, admin)")
async def list_models(_guard: AdminOnly, session: DbSession) -> ModelsOut:
    _ = session  # сессия не нужна, зависимость для единообразия DI
    provider = OpenAICompatProvider()
    items = [
        ModelOut(
            tier=spec.tier,
            slug=spec.slug,
            display=spec.display,
            role=spec.role,
            configured=bool(spec.slug),
            priceIn=_fmt(spec.price_in),
            priceOut=_fmt(spec.price_out),
        )
        for spec in MODELS.values()
    ]
    return ModelsOut(
        providerConfigured=provider.is_configured(),
        currency="RUB",
        models=items,
    )


def _fmt(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.4f}"


class LLMTierHealthOut(CamelModel):
    tier: str
    slug: str
    available: bool | None


class LLMLastCallOut(CamelModel):
    at: datetime | None
    route: str | None
    modelUsed: str | None
    status: str | None
    latencyMs: int | None


class LLMUsageTodayOut(CamelModel):
    tokensIn: int
    tokensOut: int
    costTotal: str


class LLMHealthOut(CamelModel):
    status: str  # ok | degraded | echo
    providerConfigured: bool
    baseUrl: str
    availableModels: list[str]
    tiers: list[LLMTierHealthOut]
    missingModels: list[str]
    lastCall: LLMLastCallOut
    latencyP95Ms: int | None
    today: LLMUsageTodayOut
    budgetFreeTokensDay: int
    budgetProTokensDay: int


@router.get(
    "/llm/health",
    summary="Живой статус LLM-провайдера и моделей (S-31, admin)",
)
async def llm_health(_guard: AdminOnly, session: DbSession) -> LLMHealthOut:
    """Проверяет провайдера (GET /models) и сверяет слаги тиров.

    Без ``LLM_BASE_URL`` — ``status=echo`` (шлюз работает на заглушке).
    Провайдер недоступен/слаги не найдены — ``degraded``. Сеть ограничена
    таймаутом 5 с, чтобы health не подвешивал админку.
    """
    provider = get_cloud_provider()
    configured = provider.is_configured()
    available: set[str] | None = None
    if configured:
        try:
            available = set(
                await asyncio.wait_for(provider.list_models(), timeout=5.0)
            )
        except Exception as exc:  # noqa: BLE001 - health не должен падать
            logger.warning("llm health: list_models failed: %s", exc)

    tiers: list[LLMTierHealthOut] = []
    missing: list[str] = []
    for spec in MODELS.values():
        is_available = (spec.slug in available) if available is not None else None
        if configured and available is not None and spec.slug not in available:
            missing.append(spec.slug)
        tiers.append(
            LLMTierHealthOut(
                tier=spec.tier,
                slug=spec.slug,
                available=is_available,
            )
        )

    if not configured:
        status = "echo"
    elif available is None or missing:
        status = "degraded"
    else:
        status = "ok"

    last = (
        await session.execute(select(LLMCall).order_by(LLMCall.id.desc()).limit(1))
    ).scalar_one_or_none()
    last_call = LLMLastCallOut(
        at=last.created_at if last else None,
        route=last.route if last else None,
        modelUsed=last.model_used if last else None,
        status=last.status if last else None,
        latencyMs=last.latency_ms if last else None,
    )

    recent_latencies = sorted(
        latency
        for latency in (
            await session.execute(
                select(LLMCall.latency_ms)
                .where(LLMCall.status == economy.STATUS_OK, LLMCall.latency_ms > 0)
                .order_by(LLMCall.id.desc())
                .limit(100)
            )
        ).scalars()
        if latency is not None
    )
    latency_p95 = (
        recent_latencies[
            min(len(recent_latencies) - 1, math.ceil(len(recent_latencies) * 0.95) - 1)
        ]
        if recent_latencies
        else None
    )

    today_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    usage_in, usage_out, usage_cost = (
        await session.execute(
            select(
                func.coalesce(func.sum(LLMCall.tokens_in), 0),
                func.coalesce(func.sum(LLMCall.tokens_out), 0),
                func.coalesce(
                    func.sum(
                        func.coalesce(LLMCall.cost_in, 0)
                        + func.coalesce(LLMCall.cost_out, 0)
                    ),
                    0,
                ),
            ).where(LLMCall.created_at >= today_start)
        )
    ).one()

    return LLMHealthOut(
        status=status,
        providerConfigured=configured,
        baseUrl=provider.base_url,
        availableModels=sorted(available)[:50] if available is not None else [],
        tiers=tiers,
        missingModels=sorted(set(missing)),
        lastCall=last_call,
        latencyP95Ms=latency_p95,
        today=LLMUsageTodayOut(
            tokensIn=int(usage_in),
            tokensOut=int(usage_out),
            costTotal=f"{Decimal(usage_cost):.4f}",
        ),
        budgetFreeTokensDay=settings.budget_free_tokens_day,
        budgetProTokensDay=settings.budget_pro_tokens_day,
    )


class FinOpsDayOut(CamelModel):
    day: str
    users: int
    tokensIn: int
    tokensOut: int
    costTotal: str


class FinOpsOut(CamelModel):
    currency: str
    days: list[FinOpsDayOut]


@router.get(
    "/finops/usage",
    summary="Расход по дням (Design §8.5/§12.2, admin)",
)
async def finops_usage(
    _guard: AdminOnly,
    session: DbSession,
    days: int = Query(default=7, ge=1, le=90),
) -> FinOpsOut:
    rows = await economy.finops_daily(session, days)
    return FinOpsOut(
        currency=settings.llm_cost_currency,
        days=[
            FinOpsDayOut(
                day=row[0].isoformat(),
                users=int(row[1]),
                tokensIn=int(row[2] or 0),
                tokensOut=int(row[3] or 0),
                costTotal=f"{Decimal(row[4] or 0):.4f}",
            )
            for row in rows
        ],
    )
