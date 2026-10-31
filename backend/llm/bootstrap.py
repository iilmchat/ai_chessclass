"""Бутстрап-проверка слагов моделей (Design §8.3, риск R-01).

GET {LLM_BASE_URL}/models → сравнение со слагами реестра;
несуществующий слаг → warning + автопропуск (модель недоступна).
"""

import logging

from llm.client import OpenAICompatProvider
from llm.models_registry import MODELS

logger = logging.getLogger(__name__)


async def validate_model_slags(provider: OpenAICompatProvider | None = None) -> dict[str, bool]:
    """Вернуть карту tier → слаг найден у провайдера; расхождения — в логи."""
    provider = provider or OpenAICompatProvider()
    try:
        available = set(await provider.list_models())
    except Exception as exc:  # noqa: BLE001 — бутстрап не роняет старт
        logger.warning("llm bootstrap: провайдер недоступен (%s) — слаги не проверены", exc)
        return {}

    result: dict[str, bool] = {}
    for tier, spec in MODELS.items():
        if not spec.slug:
            logger.warning(
                "llm bootstrap: %s (%s) — слаг не задан (env LLM_MODEL_*)", tier, spec.display
            )
            result[tier] = False
            continue
        if spec.slug in available:
            result[tier] = True
            logger.info("llm bootstrap: %s → %s — ок", tier, spec.slug)
        else:
            result[tier] = False
            logger.warning(
                "llm bootstrap: %s → слаг %r не найден у провайдера (%s) — автопропуск",
                tier, spec.slug, spec.display,
            )
    return result
