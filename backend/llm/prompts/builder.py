"""Сборщик сообщений для шлюза (порт build_messages из teacher).

build_messages(route, level, request, user_input, facts, knowledge, history)
→ [system, …history, user]. Контекст: последние MAX_CONTEXT_MESSAGES, каждое
— до MAX_MESSAGE_CHARS. Параметры вызова по маршруту — ROUTE_PARAMS (SPEC §6.5).

S-71 (ADR-018): user content структурно разделён на trusted-инструкции/факты
и untrusted-блоки (ввод ученика, RAG). Недоверенный текст санитизируется
`llm/security.py`; системный промпт содержит правила изоляции.
"""

from dataclasses import dataclass

from core.levels import Level
from llm.base import LLMMessage
from llm.prompts.levels import get_level_rules
from llm.prompts.templates import build_system_prompt
from llm.security import (
    redact_secrets,
    sanitize_trusted_text,
    sanitize_untrusted_text,
)

#: Сколько последних сообщений диалога попадает в контекст (порт teacher)
MAX_CONTEXT_MESSAGES = 20

#: Ограничение длины одного сообщения в контексте (символов)
MAX_MESSAGE_CHARS = 4000

FACTS_HEADER = "Факты (проверенные данные, менять нельзя):"
KNOWLEDGE_HEADER = "Полезный материал (база знаний):"

#: Имена блоков структурной изоляции (S-71, ADR-018).
TRUSTED_INSTRUCTIONS_TAG = "trusted_instructions"
TRUSTED_FACTS_TAG = "trusted_facts"
UNTRUSTED_USER_INPUT_TAG = "untrusted_user_input"
UNTRUSTED_RAG_CONTEXT_TAG = "untrusted_rag_context"


@dataclass(frozen=True, slots=True)
class RouteParams:
    temperature: float
    max_tokens: int


#: параметры генерации по маршруту (таблица — SPEC §6.5)
ROUTE_PARAMS: dict[str, RouteParams] = {
    "python_teacher.comment": RouteParams(temperature=0.3, max_tokens=400),
    "python_teacher.hint": RouteParams(temperature=0.3, max_tokens=300),
    "python_teacher.explain_code": RouteParams(temperature=0.2, max_tokens=700),
    "chess_lab.insight": RouteParams(temperature=0.4, max_tokens=600),
    "chess_lab.next_moves": RouteParams(temperature=0.3, max_tokens=400),
    "chess_lab.blunder": RouteParams(temperature=0.3, max_tokens=400),
    "chess_lab.commentary": RouteParams(temperature=0.5, max_tokens=500),
    "chess_lab.study": RouteParams(temperature=0.5, max_tokens=300),
    "bot_lab.coach": RouteParams(temperature=0.4, max_tokens=600),
    "anticheat.judge_explain": RouteParams(temperature=0.1, max_tokens=300),
    "reports.parent_summary": RouteParams(temperature=0.3, max_tokens=500),
}


def get_route_params(route: str) -> RouteParams:
    params = ROUTE_PARAMS.get(route)
    if params is None:
        raise KeyError(f"Нет параметров генерации для маршрута {route!r}")
    return params


def _block(tag: str, body: str) -> str:
    return f"<{tag}>\n{body}\n</{tag}>"


def _clean_trusted(text: str) -> str:
    return redact_secrets(sanitize_trusted_text(text))


def _clean_untrusted(text: str) -> str:
    return redact_secrets(sanitize_untrusted_text(text))


def build_user_content(
    request: str,
    facts: list[str] | None = None,
    knowledge: list[str] | None = None,
    user_input: str | None = None,
) -> str:
    """Собрать user-сообщение в структурной разметке trusted/untrusted.

    ``request`` — инструкция, сгенерированная backend-ом (trusted).
    ``user_input`` — текст/код ученика (untrusted), ``knowledge`` — RAG
    (untrusted), ``facts`` — факты движка/тестов (trusted).
    """
    parts: list[str] = [_block(TRUSTED_INSTRUCTIONS_TAG, _clean_trusted(request))]
    if facts:
        facts_body = "\n".join(
            [FACTS_HEADER, *(f"- {_clean_trusted(fact)}" for fact in facts)]
        )
        parts.append(_block(TRUSTED_FACTS_TAG, facts_body))

    parts.append(
        _block(UNTRUSTED_USER_INPUT_TAG, _clean_untrusted(user_input or ""))
    )

    knowledge_body = [KNOWLEDGE_HEADER]
    if knowledge:
        knowledge_body.extend(f"- {_clean_untrusted(item)}" for item in knowledge)
    parts.append(_block(UNTRUSTED_RAG_CONTEXT_TAG, "\n".join(knowledge_body)))
    return "\n\n".join(parts)


def build_messages(
    route: str,
    level: Level,
    request: str,
    *,
    user_input: str | None = None,
    facts: list[str] | None = None,
    knowledge: list[str] | None = None,
    history: list[LLMMessage] | None = None,
) -> list[LLMMessage]:
    """Собрать список сообщений: system(маршрут×уровень) + история + user.

    ``knowledge`` — RAG-контекст (Design §8.6), ``user_input`` — код/вопрос
    ученика (S-71). Оба блока помечены как untrusted и санитизированы.
    """
    rules = get_level_rules(level)
    messages = [
        LLMMessage(role="system", content=build_system_prompt(route, rules.rules))
    ]
    for message in (history or [])[-MAX_CONTEXT_MESSAGES:]:
        messages.append(
            LLMMessage(role=message.role, content=message.content[:MAX_MESSAGE_CHARS])
        )
    messages.append(
        LLMMessage(
            role="user",
            content=build_user_content(request, facts, knowledge, user_input)[
                : MAX_MESSAGE_CHARS * 2
            ],
        )
    )
    return messages
