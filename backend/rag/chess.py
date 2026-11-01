"""Chess-знания (S-39): запрос к RAG по FEN/фазе/теме.

FEN не является текстом для embedding-модели, поэтому формируем
русскоязычный запрос: фаза, материал, тема (insight/blunder) и ключевые
термины. Документы — seed-база `rag_documents(domain=chess)`.
"""

import logging
import re

import chess
from sqlalchemy.ext.asyncio import AsyncSession

from rag import retrieval

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_SUFFIXES = (
    "ами",
    "ями",
    "ого",
    "его",
    "ому",
    "ему",
    "ыми",
    "ими",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ой",
    "ей",
    "ий",
    "ый",
    "ов",
    "ев",
    "ам",
    "ям",
    "ах",
    "ях",
    "ом",
    "ем",
    "а",
    "я",
    "о",
    "е",
    "ы",
    "и",
    "у",
    "ю",
    "ь",
)


def _stem(token: str) -> str:
    token = token.lower()
    for suffix in _SUFFIXES:
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _tokens(text: str) -> set[str]:
    return {_stem(token) for token in _TOKEN_RE.findall(text)}


def _rerank(
    query: str, hits: list[dict], *, phase: str | None = None
) -> list[dict]:
    """Лексический rerank поверх hash/embedding-поиска."""
    query_tokens = _tokens(query)
    phase_word = PHASE_RU.get(phase, "") if phase else ""

    def score(hit: dict) -> float:
        title = str(hit.get("titleRu") or "")
        text = str(hit.get("text") or "")
        title_tokens = _tokens(title)
        body_tokens = _tokens(text)
        lexical = len(query_tokens & body_tokens)
        title_overlap = len(query_tokens & title_tokens)
        phase_boost = 6 if phase_word and phase_word in title.lower() else 0
        return (
            lexical * 2
            + title_overlap * 4
            + phase_boost
            + float(hit.get("similarity") or 0)
        )

    return sorted(hits, key=score, reverse=True)


PHASE_RU = {
    "opening": "дебют",
    "middlegame": "миттельшпиль",
    "endgame": "эндшпиль",
}


def detect_phase(fen: str) -> str:
    """Грубая фаза по числу фигур/материалу и номеру хода."""
    try:
        board = chess.Board(fen)
    except ValueError:
        return "middlegame"
    pieces = len(board.piece_map())
    material = sum(
        {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9}.get(p.symbol().lower(), 0)
        for p in board.piece_map().values()
    )
    if board.fullmove_number <= 12 and pieces >= 24:
        return "opening"
    if pieces <= 12 or material <= 20:
        return "endgame"
    return "middlegame"


def build_chess_query(fen: str, topic: str | None = None) -> str:
    """Текстовый запрос для hash/embedding retrieval."""
    phase = detect_phase(fen)
    parts = [f"шахматы {PHASE_RU[phase]}", "план", "оценка позиции"]
    if phase == "opening":
        parts += ["развитие фигур", "центр", "рокировка"]
    elif phase == "endgame":
        parts += ["активность короля", "пешки", "оппозиция"]
    else:
        parts += ["активность фигур", "слабые поля", "атака"]
    if topic:
        parts.append(topic)
    try:
        board = chess.Board(fen)
        if board.is_check():
            parts.append("шах королю")
        if board.is_checkmate():
            parts.append("мат")
    except ValueError:
        pass
    return " ".join(parts)


async def search_chess_text(
    session: AsyncSession,
    query: str,
    *,
    k: int = 3,
    phase: str | None = None,
) -> list[dict]:
    """RAG-поиск по текстовому запросу + лексический rerank."""
    hits = await retrieval.search(
        session,
        query,
        k=max(k * 10, 50),
        domains=["chess"],
    )
    return _rerank(query, hits, phase=phase)[:k]


async def search_chess_knowledge(
    session: AsyncSession,
    fen: str,
    *,
    k: int = 3,
    topic: str | None = None,
) -> list[dict]:
    """RAG-поиск знаний по позиции; ошибка RAG не ломает insight."""
    try:
        return await search_chess_text(
            session,
            build_chess_query(fen, topic),
            k=k,
            phase=detect_phase(fen),
        )
    except Exception as exc:  # noqa: BLE001 - RAG не критичен для ответа
        logger.warning("chess RAG: поиск не удался: %s", exc)
        return []
