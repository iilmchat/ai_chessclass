"""Реестр моделей шлюза: слаги (env), цены ₽/1M (Numeric(12,4), Design §8.3).

Точные слаги RouterAI — риск R-01: сверяются на бутстрапе (llm/bootstrap);
цены judge/L3-alt Design не фиксирует (None → заполняются через env).
"""

from dataclasses import dataclass
from decimal import Decimal

from core.config import settings


@dataclass(frozen=True, slots=True)
class ModelSpec:
    tier: str  # L1 | L2 | L3 | L3_alt | judge
    slug: str
    display: str
    role: str
    price_in: Decimal | None   # ₽ / 1M input tokens
    price_out: Decimal | None  # ₽ / 1M output tokens


def build_models_registry() -> dict[str, ModelSpec]:
    """Собрать реестр из настроек (slug/цены живут в env — Design §8.3)."""
    models = {
        "L1": ModelSpec(
            tier="L1",
            slug=settings.llm_model_l1,
            display="MiniMax M3.1 Flash",
            role="комментарии/подсказки (массовые)",
            price_in=settings.llm_cost_l1_in,
            price_out=settings.llm_cost_l1_out,
        ),
        "L2": ModelSpec(
            tier="L2",
            slug=settings.llm_model_l2,
            display="DeepSeek V4.1 Flash",
            role="инсайты, разборы, бот-coach",
            price_in=settings.llm_cost_l2_in,
            price_out=settings.llm_cost_l2_out,
        ),
        "L3": ModelSpec(
            tier="L3",
            slug=settings.llm_model_l3,
            display="Beam 1.0 501B",
            role="advanced-ученикам, сложные разборы",
            price_in=settings.llm_cost_l3_in,
            price_out=settings.llm_cost_l3_out,
        ),
        "L3_alt": ModelSpec(
            tier="L3_alt",
            slug=settings.llm_model_l3_alt,
            display="Claude Sonnet 5.5",
            role="резерв/проверка качества L3",
            price_in=settings.llm_cost_l3_alt_in,
            price_out=settings.llm_cost_l3_alt_out,
        ),
        "judge": ModelSpec(
            tier="judge",
            slug=settings.llm_model_judge,
            display="Decider Flash V1.2",
            role="античит-judge, короткие сессии",
            price_in=settings.llm_cost_judge_in,
            price_out=settings.llm_cost_judge_out,
        ),
    }
    return models


MODELS: dict[str, ModelSpec] = build_models_registry()

TIERS: tuple[str, ...] = ("L1", "L2", "L3", "L3_alt", "judge")
