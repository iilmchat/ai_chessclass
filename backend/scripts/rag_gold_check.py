"""S-64: сверка gold-set (rag/eval_cases) с корпусом: каждая подстрока
должна существовать в сидовом корпусе (иначе кейс мёртв, а не «не найден»).

Запуск из контейнера/CI: python scripts/rag_gold_check.py — при нес.findBy
находит мёртвый кейс и возвращает 1 (для RULES §6 pre-commit или отдельный
CI-шаг S-63-расширения).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa  # noqa: E402

from core.db import session_factory  # noqa: E402
from rag.eval_cases import GOLD_SET  # noqa: E402


async def main() -> int:
    from rag.models import RagDocument

    async with session_factory() as session:
        texts = (
            (
                await session.execute(
                    sa.select(RagDocument.text).where(RagDocument.status == "published")
                )
            )
            .scalars()
            .all()
        )
    corpus = "\n".join(texts).lower()

    dead = [
        (query, expected)
        for query, expected in GOLD_SET
        if expected.lower() not in corpus
    ]
    if dead:
        for query, expected in dead:
            print(f"[DEAD] {query!r}: подстрока {expected!r} не в корпусе")
        print(f"мёртвых кейсов: {len(dead)}/{len(GOLD_SET)}")
        return 1

    print(f"gold-set: {len(GOLD_SET)} кейсов — все подстроки в корпусе (published)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
