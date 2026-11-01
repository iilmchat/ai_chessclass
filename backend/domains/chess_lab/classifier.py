"""Классификация ходов по Δeval (порт идеи SPEC annotator §2.2).

Пороги: best (сыгран лучший ход) · good <50 · inaccuracy <100 ·
mistake <CH_BLUNDER_CP · blunder ≥ CH_BLUNDER_CP (config, §9.2 «пороги —
параметры config»).
"""

from core.config import settings


def classify_move(delta_cp: int, *, is_best: bool) -> str:
    if is_best:
        return "best"
    if delta_cp >= settings.chess_blunder_cp:
        return "blunder"
    if delta_cp >= 100:
        return "mistake"
    if delta_cp >= 50:
        return "inaccuracy"
    return "good"
