"""Embeddings 768 (ADR-006): провайдер (OpenAI-compat) с hash-фолбэком.

Dev/CI без LLM-ключа: детерминированный hash-эмбеддер (bag-of-words с
нормализацией) — пайплайн ingest/retrieval работает end-to-end; при
настроенном провайдере используется модель `LLM_EMBED_MODEL` (§18.2 —
открытый вопрос, слаг задаётся env).
"""

import hashlib
import logging
import math
import re

from core.config import settings

logger = logging.getLogger(__name__)

EMBED_DIM = 768
_TOKEN_RE = re.compile(r"\w+")


def hash_embedding(text: str) -> list[float]:
    """Детерминированный 768-вектор (bag-of-words, L2-нормализация)."""
    vector = [0.0] * EMBED_DIM
    for token in _TOKEN_RE.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBED_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]


class EmbeddingProvider:
    """Единая точка получения эмбеддингов (gateway-транспорт + фолбэк)."""

    def __init__(self) -> None:
        from llm.client import OpenAICompatProvider

        self._provider = OpenAICompatProvider()

    @property
    def mode(self) -> str:
        """Провайдер ('openai') или hash-фолбэк ('hash') — фиксируется в meta."""
        if not settings.llm_embed_model:
            return "hash"
        return "openai" if self._provider.is_configured() else "hash"

    async def embed(self, texts: list[str]) -> tuple[list[list[float]], str]:
        """Эмбеддинги текстов; недоступен провайдер → hash-фолбэк (warning)."""
        if self.mode == "openai":
            try:
                vectors = await self._provider.embeddings(
                    texts, settings.llm_embed_model
                )
                return vectors, "openai"
            except Exception as exc:  # noqa: BLE001 — фолбэк не роняет инжест
                logger.warning("rag: embeddings провайдер недоступен (%s) — hash", exc)
        return [hash_embedding(t) for t in texts], "hash"
