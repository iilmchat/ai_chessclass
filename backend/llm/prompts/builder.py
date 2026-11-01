"""Сборщик сообщений для шлюза (порт build_messages из teacher).

build_messages(route, level, request, facts, history) → [system, …history, user].
Контекст: последние MAX_CONTEXT_MESSAGES, каждое — до MAX_MESSAGE_CHARS.
Параметры вызова по маршруту — ROUTE_PARAMS (таблица — SPEC §6.5).
"""

from dataclasses import dataclass

from core.levels import Level
from llm.base import LLMMessage
from llm.prompts.levels import get_level_rules
from llm.prompts.templates import build_system_prompt

#: Сколько последних сообщений диалога попадает в контекст (порт teacher)
MAX_CONTEXT_MESSAGES = 20

#: Ограничение длины одного сообщения в контексте (символов)
MAX_MESSAGE_CHARS = 4000

FACTS_HEADER = "Факты (проверенные данные, менять нельзя):"
KNOWLEDGE_HEADER = "Полезный материал (база знаний):"


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
    "bot_lab.coach": RouteParams(temperature=0.4, max_tokens=600),
    "anticheat.judge_explain": RouteParams(temperature=0.1, max_tokens=300),
    "reports.parent_summary": RouteParams(temperature=0.3, max_tokens=500),
}


def get_route_params(route: str) -> RouteParams:
    params = ROUTE_PARAMS.get(route)
    if params is None:
        raise KeyError(f"Нет параметров генерации для маршрута {route!r}")
    return params


def build_user_content(
    request: str,
    facts: list[str] | None = None,
    knowledge: list[str] | None = None,
) -> str:
    """Запрос + блок базы знаний (RAG, §8.6) + блок фактов (движок/тесты)."""
    parts: list[str] = [request]
    if knowledge:
        parts.append(KNOWLEDGE_HEADER)
        parts.extend(f"- {item}" for item in knowledge)
    if facts:
        parts.append(FACTS_HEADER)
        parts.extend(f"- {fact}" for fact in facts)
    return "\n".join(parts)


def build_messages(
    route: str,
    level: Level,
    request: str,
    *,
    facts: list[str] | None = None,
    knowledge: list[str] | None = None,
    history: list[LLMMessage] | None = None,
) -> list[LLMMessage]:
    """Собрать список сообщений: system(маршрут×уровень) + история + user.

    knowledge — RAG-контекст (Design §8.6): вставляется перед фактами,
    чтобы модель опиралась на материал базы знаний, не трогая факты.
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
            content=build_user_content(request, facts, knowledge)[
                : MAX_MESSAGE_CHARS * 2
            ],
        )
    )
    return messages
