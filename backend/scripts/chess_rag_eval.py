"""S-39: eval chess-знаний (10 текстовых запросов + 3 FEN-фазы).

Запуск после seed:
    python scripts/chess_rag_eval.py
Проверяет top-1 title по ожидаемой теме; exit 1 при MISS.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import session_factory  # noqa: E402
from rag.chess import search_chess_knowledge, search_chess_text  # noqa: E402

TEXT_QUERIES: list[tuple[str, str]] = [
    ("развитие фигур в дебюте", "Дебют"),
    ("план в миттельшпиле", "Миттельшпиль"),
    ("активность короля в эндшпиле", "Эндшпиль"),
    ("безопасность короля и рокировка", "Король"),
    ("изолированная пешка", "Пешечная структура"),
    ("как считать варианты", "Расчёт"),
    ("профилактика зевков", "Профилактика"),
    ("оценка позиции материал активность", "Оценка"),
    ("вилка связка двойной удар", "Тактика"),
    ("атака на короля", "Атака"),
]

FEN_QUERIES: list[tuple[str, str, str]] = [
    (
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "Дебют",
        "start",
    ),
    (
        "r1bq1rk1/ppp2ppp/2n2n2/3pp3/8/2NBPN2/PPP2PPP/R1BQ1RK1 w - - 0 20",
        "Миттельшпиль",
        "middlegame",
    ),
    (
        "8/8/8/4k3/8/4K3/4P3/8 w - - 0 1",
        "Эндшпиль",
        "endgame",
    ),
]


async def main() -> int:
    misses = 0
    async with session_factory() as session:
        for query, expected in TEXT_QUERIES:
            hits = await search_chess_text(session, query, k=3)
            title = hits[0]["titleRu"] if hits else "-"
            ok = expected.lower() in title.lower()
            misses += 0 if ok else 1
            print(f"[{'OK' if ok else 'MISS'}] {query!r} -> {title}")
            if not ok:
                print("  top3:", [hit["titleRu"] for hit in hits[:3]])
        for fen, expected, label in FEN_QUERIES:
            hits = await search_chess_knowledge(session, fen, k=3)
            title = hits[0]["titleRu"] if hits else "-"
            ok = expected.lower() in title.lower()
            misses += 0 if ok else 1
            print(f"[{'OK' if ok else 'MISS'}] FEN {label} -> {title}")
            if not ok:
                print("  top3:", [hit["titleRu"] for hit in hits[:3]])
    print(f"chess-rag eval: {len(TEXT_QUERIES) + len(FEN_QUERIES) - misses}"
          f"/{len(TEXT_QUERIES) + len(FEN_QUERIES)} OK")
    return 0 if misses == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
