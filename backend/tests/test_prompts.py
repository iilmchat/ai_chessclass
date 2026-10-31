"""Промпты (DoD S-06): comment/hint/insight выдают промпт по уровню;
параметры генерации по маршрутам; контекстные лимиты; echo как dev-заглушка."""

import pytest

from core.db import session_factory
from core.levels import Level
from llm.base import LLMMessage
from llm.gateway import LLMCallContext, llm_generate
from llm.prompts.builder import (
    MAX_CONTEXT_MESSAGES,
    MAX_MESSAGE_CHARS,
    ROUTE_PARAMS,
    build_messages,
    get_route_params,
)
from llm.prompts.templates import PROMPT_VERSIONS, ROLE_BY_ROUTE
from llm.routes import ROUTES


def _system(route: str, level: Level) -> str:
    return build_messages(route, level, "Тест")[0].content


def test_comment_prompt_differs_by_level():
    novice = _system("python_teacher.comment", Level.NOVICE)
    advanced = _system("python_teacher.comment", Level.ADVANCED)
    assert "Готовое решение не давать" in novice
    assert "Полное решение" in advanced
    assert novice != advanced


def test_hint_prompt_by_level():
    novice = _system("python_teacher.hint", Level.NOVICE)
    advanced = _system("python_teacher.hint", Level.ADVANCED)
    # novice: лестница подсказок без готового кода
    assert "подсказку" in novice and "Готовое решение не давать" in novice
    # advanced: код разрешён
    assert "Полное решение" in advanced


def test_insight_prompt_facts_rule():
    system = _system("chess_lab.insight", Level.INTERMEDIATE)
    assert "Факты движка менять нельзя" in system
    messages = build_messages(
        "chess_lab.insight",
        Level.INTERMEDIATE,
        "Объясни позицию",
        facts=["eval: +1.2", "best: e2e4"],
    )
    user = messages[-1].content
    assert "Факты (проверенные данные" in user
    assert "- eval: +1.2" in user


def test_all_routes_have_params_and_versions():
    assert set(ROUTE_PARAMS) == set(ROUTES) == set(ROLE_BY_ROUTE)
    assert set(PROMPT_VERSIONS) == set(ROUTES)
    for route, version in PROMPT_VERSIONS.items():
        assert version >= 1, route


def test_judge_params_low_temperature():
    assert ROUTE_PARAMS["anticheat.judge_explain"].temperature <= 0.2


def test_unknown_route_params_raises():
    with pytest.raises(KeyError):
        get_route_params("chess_lab.teleport")


def test_context_limits():
    history = [
        LLMMessage(role="user", content=f"msg {i} " + "x" * 5000)
        for i in range(30)
    ]
    messages = build_messages("chess_lab.commentary", Level.NOVICE, "вопрос", history=history)
    # system + последние 20 истории + user
    assert len(messages) == MAX_CONTEXT_MESSAGES + 2
    history_part = messages[1:-1]
    assert all(len(m.content) <= MAX_MESSAGE_CHARS for m in history_part)
    assert messages[0].role == "system" and messages[-1].role == "user"


async def test_echo_uses_built_prompt(redis_client):
    """Echo-режим как dev-заглушка: собранный промпт доходит до шлюза
    (в контейнере LLM_BASE_URL пуст → естественный echo)."""
    messages = build_messages(
        "python_teacher.hint",
        Level.NOVICE,
        "Как сделать цикл?",
        facts=["задание: FizzBuzz"],
    )
    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.hint",
            level=Level.NOVICE,
            messages=messages,
            ctx=LLMCallContext(),
        )
    assert result.status == "echo"
    assert "Как сделать цикл?" in result.text


async def test_gateway_passes_route_params():
    """build_messages + get_route_params — полный комплект для llm_generate."""
    messages = build_messages("python_teacher.comment", Level.NOVICE, "код: print(1)")
    params = get_route_params("python_teacher.comment")
    assert params.temperature == 0.3 and params.max_tokens == 400
    assert messages[0].role == "system"
