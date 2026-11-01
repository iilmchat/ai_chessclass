"""Живой smoke LLM-шлюза (S-31): 4 маршрута (L1/L2/L3/judge).

Запуск (в контейнере с БД/Redis и env LLM_*):
    docker compose -f docker-compose.dev.yml run --rm api python scripts/llm_smoke.py

Коды возврата: 0 — все вызовы ``status=ok``; 2 — echo/degraded (диагностика
в stdout). Скрипт пишет строки в ``llm_calls`` (FinOps) и не трогает квоты
пользователей (user_id=None).
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redis.asyncio as redis_lib  # noqa: E402

import domains.auth.models  # noqa: E402,F401 - регистрирует users для FK llm_calls
from core.config import settings  # noqa: E402
from core.db import engine, session_factory  # noqa: E402
from core.levels import Level  # noqa: E402
from llm.gateway import (  # noqa: E402
    LLMCallContext,
    close_llm_providers,
    get_cloud_provider,
    llm_generate,
)
from llm.prompts.builder import build_messages  # noqa: E402

CASES: list[tuple[str, Level, str]] = [
    (
        "python_teacher.comment",
        Level.NOVICE,
        "Ученик написал: print('Привет'). Что здесь хорошо и что улучшить?",
    ),
    (
        "python_teacher.explain_code",
        Level.INTERMEDIATE,
        "Объясни, что делает код и где он может пригодиться:\n"
        "for i in range(3):\n    print(i)",
    ),
    (
        "chess_lab.insight",
        Level.ADVANCED,
        "Стартовая позиция. Назови один ключевой принцип развития фигур.",
    ),
    (
        "anticheat.judge_explain",
        Level.NOVICE,
        "Ученик утверждает, что написал цикл for самостоятельно. "
        "Задай один уточняющий вопрос по его коду.",
    ),
]


async def main() -> int:
    provider = get_cloud_provider()
    if not provider.is_configured():
        print(
            "llm smoke: LLM_BASE_URL не задан — шлюз в echo-режиме. "
            "Заполните .env (RouterAI или LM Studio), затем повторите.",
            file=sys.stderr,
        )
        return 2

    print(f"llm smoke: provider={provider.base_url}")
    redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    failed = 0
    try:
        async with session_factory() as session:
            for route, level, request in CASES:
                started = time.monotonic()
                result = await llm_generate(
                    session,
                    redis,
                    route=route,
                    level=level,
                    messages=build_messages(route, level, request=request),
                    ctx=LLMCallContext(
                        user_id=None, billing_tier="free", task_kind="sync"
                    ),
                )
                await session.commit()
                latency = int((time.monotonic() - started) * 1000)
                ok = result.status == "ok"
                failed += 0 if ok else 1
                print(
                    f"[{'ok' if ok else 'FAIL'}] {route} ({level.value}/{result.tier}): "
                    f"status={result.status} model={result.model_used} "
                    f"latency={latency}ms "
                    f"tokens={result.usage.prompt_tokens}/{result.usage.completion_tokens}"
                )
                print(f"       {result.text[:180].replace(chr(10), ' ')}")
    finally:
        await close_llm_providers()
        await redis.aclose()
        await engine.dispose()

    if failed:
        print(f"llm smoke: FAILED ({failed}/{len(CASES)})", file=sys.stderr)
        return 2
    print(f"llm smoke: OK ({len(CASES)}/{len(CASES)})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
