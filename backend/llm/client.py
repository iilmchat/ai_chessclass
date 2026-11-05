"""OpenAI-совместимый транспорт (RouterAI / LM Studio) на httpx.

Ретрай: 1 повтор с экспоненциальным backoff и jitter (Design §8.4);
общий таймаут LLM_TIMEOUT_S. Транспорт инъекцируется (httpx.MockTransport).
"""

import asyncio
import logging
import random

import httpx

from core.config import settings
from core.egress import hostname_of, make_egress_hook
from llm.base import LLMMessage, LLMProvider, LLMUnavailableError, LLMUsage

logger = logging.getLogger(__name__)


class OpenAICompatProvider(LLMProvider):
    """Единый клиент к OpenAI-совместимому API (cloud или local)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        if api_key is None:
            # S-78: при совпадении base_url с локальным провайдером берём
            # LLM_LOCAL_API_KEY; иначе — облачный LLM_API_KEY.
            local_base = settings.llm_local_base_url.rstrip("/")
            api_key = (
                settings.llm_local_api_key
                if self.base_url == local_base
                else settings.llm_api_key
            )
        self.api_key = api_key
        self.name = "openai_compat"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=(
                {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            ),
            timeout=httpx.Timeout(settings.llm_timeout_s),
            transport=transport,
            # S-61: egress allowlist; собственный base_url клиента разрешён
            # явно (админ конфигурирует провайдера намеренно).
            event_hooks={
                "request": [make_egress_hook(hostname_of(self.base_url) or "")]
            },
        )

    def is_configured(self) -> bool:
        return bool(self.base_url) and not self.base_url.startswith("change_me")

    async def generate(
        self,
        model: str,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, LLMUsage]:
        if not self.is_configured():
            raise LLMUnavailableError("LLM_BASE_URL не настроен")
        if not model:
            raise LLMUnavailableError("Слаг модели не задан (env LLM_MODEL_*)")

        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        last_error: Exception | None = None
        for attempt in (1, 2):  # 1 retry (Design §8.4)
            try:
                response = await self._client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"].get("content")
                if text is None or not str(text).strip():
                    # reasoning-модель могла израсходовать весь max_tokens;
                    # не отдаём "None" клиенту — уходим в retry/fallback.
                    raise ValueError("пустой message.content")
                usage_raw = data.get("usage") or {}
                usage = LLMUsage(
                    prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
                    completion_tokens=int(usage_raw.get("completion_tokens", 0)),
                )
                return str(text), usage
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "llm: попытка %d к %s (%s) не удалась: %s", attempt, model, self.base_url, exc
                )
                if attempt == 1:
                    # Экспонента от base_delay + jitter: не синхронизируем
                    # одновременные ретраи api/worker (S-70).
                    delay = (
                        settings.llm_retry_delay_s * (2 ** (attempt - 1))
                        + random.uniform(0, 0.5)
                    )
                    await asyncio.sleep(delay)
        raise LLMUnavailableError(f"LLM недоступен после ретрая: {last_error}") from last_error

    async def list_models(self) -> list[str]:
        if not self.is_configured():
            raise LLMUnavailableError("LLM_BASE_URL не настроен")
        response = await self._client.get("/models")
        response.raise_for_status()
        data = response.json()
        return [str(item["id"]) for item in data.get("data", [])]

    async def embeddings(self, texts: list[str], model: str) -> list[list[float]]:
        """OpenAI-совместимый /embeddings: список векторов по текстам."""
        if not self.is_configured():
            raise LLMUnavailableError("LLM_BASE_URL не настроен")
        response = await self._client.post(
            "/embeddings", json={"model": model, "input": texts}
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]

    async def close(self) -> None:
        await self._client.aclose()
