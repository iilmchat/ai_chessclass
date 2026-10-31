"""Единый шлюз (Design §8.1): generate(route, level, messages) → текст.

Домены не знают моделей — только маршрут и уровень (ADR-004).
Fallback-цепочка cloud → local → echo и запись llm_calls — этап S-05.
"""

from dataclasses import dataclass

from core.levels import Level
from llm.base import LLMMessage, LLMProvider, LLMUsage
from llm.models_registry import MODELS
from llm.routes import resolve_tier


@dataclass(frozen=True, slots=True)
class LLMResult:
    route: str
    level: Level
    tier: str
    model_requested: str  # слаг из реестра
    model_used: str       # фактически обслуживший (S-05: может отличаться)
    text: str
    usage: LLMUsage


class LLMGateway:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def generate(
        self,
        route: str,
        level: Level,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        tier = resolve_tier(route, level)
        spec = MODELS[tier]
        text, usage = await self.provider.generate(
            spec.slug,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return LLMResult(
            route=route,
            level=level,
            tier=tier,
            model_requested=spec.slug,
            model_used=spec.slug,
            text=text,
            usage=usage,
        )

    async def close(self) -> None:
        await self.provider.close()
