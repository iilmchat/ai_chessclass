"""Контракт LLM-слоя (порт app/services/llm/base.py из teacher).

Провайдер отвечает только за транспорт к модели; образовательная логика
(уровни, маршруты, промпты) — в gateway и доменах (Design §8.1).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """Сообщение в формате chat-модели."""

    role: str  # 'system' | 'user' | 'assistant'
    content: str


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Расход токенов одного вызова (из поля `usage` ответа провайдера)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMError(Exception):
    """Базовая ошибка LLM-слоя."""


class LLMUnavailableError(LLMError):
    """Провайдер недоступен (сеть, ключ, таймаут, модель не настроена)."""


#: Значения-заглушки из .env.example — считаются «ключ/URL не настроен».
PLACEHOLDER_SECRETS = frozenset({"", "change_me_api_key", "your_api_key_here"})


def is_placeholder_secret(value: str) -> bool:
    """Похоже ли значение на заглушку, а не на реальный секрет."""
    normalized = value.strip().lower()
    return normalized in PLACEHOLDER_SECRETS or normalized.startswith("change_me")


class LLMProvider(ABC):
    """Интерфейс OpenAI-совместимого провайдера (RouterAI / LM Studio)."""

    name: str = "base"

    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, LLMUsage]:
        """Вернуть (текст ответа, usage)."""

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Список слагов моделей провайдера (GET /models) — для бутстрап-проверки."""

    @abstractmethod
    async def close(self) -> None:
        """Освободить ресурсы клиента."""
