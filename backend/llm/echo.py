"""Echo-провайдер (Design §8.4): dev-заглушка «промпт + факт-константа».

Последний вызов цепочки fallback: всегда доступен, не тратит токены.
"""

from llm.base import LLMMessage, LLMProvider, LLMUsage


class EchoProvider(LLMProvider):
    name = "echo"

    async def generate(
        self,
        model: str,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, LLMUsage]:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )
        text = f"[echo] заглушка LLM (S-05): запрос «{last_user[:160]}»"
        return text, LLMUsage(prompt_tokens=0, completion_tokens=0)

    async def list_models(self) -> list[str]:
        return ["echo"]

    async def close(self) -> None:
        return None
