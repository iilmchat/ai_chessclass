"""Оценка качества RAG-поиска (R-04): запросы → топ-хиты.

Запуск (контейнер, после seed):
    python scripts/rag_eval.py

Печатает для каждого запроса топ-1 заголовок и схожесть. Качество —
ручная интерпретация по seed-корпусу (соответствие темы запросу).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import session_factory  # noqa: E402
from rag import retrieval  # noqa: E402

QUERIES = [
    ("как накапливать сумму в цикле", "python", "Циклы в Python"),
    ("почему NameError", "python", "Отладка"),
    ("функция и return", "python", "Функции"),
    ("конь атакует двух фигур", "chess", "Вилки"),
    ("фигура без защиты", "chess", "Висячие фигуры"),
    ("считаю ходы вперёд", "chess", "Расчёт вариантов"),
]


async def main() -> None:
    async with session_factory() as session:
        for query, domain, expected in QUERIES:
            hits = await retrieval.search(session, query, k=3, domains=[domain])
            top = hits[0] if hits else None
            status = (
                "OK" if top and expected.lower() in top["titleRu"].lower() else "MISS"
            )
            print(
                f"[{status}] {query!r} -> "
                f"{top['titleRu'] if top else '—'} (sim {top['similarity'] if top else 0})"
            )


if __name__ == "__main__":
    asyncio.run(main())
