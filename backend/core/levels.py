"""Единый уровень ученика (Design §4.2, ADR-002) и маппинг доменных уровней.

Один enum на всю систему: novice | intermediate | advanced.
LLM-маршрутизация и тон ассистента завязаны на него; override на запрос
разрешён (опциональный `level` в теле запросов ассистента).
"""

import enum


class Level(enum.StrEnum):
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


# Доменные словари исходных проектов (§4.2)
LEVEL_TO_PYTHON: dict[Level, str] = {
    Level.NOVICE: "basic",
    Level.INTERMEDIATE: "intermediate",
    Level.ADVANCED: "advanced",
}
LEVEL_TO_CHESS: dict[Level, str] = {
    Level.NOVICE: "beginner",
    Level.INTERMEDIATE: "club",
    Level.ADVANCED: "gm",
}

PYTHON_TO_LEVEL: dict[str, Level] = {v: k for k, v in LEVEL_TO_PYTHON.items()}
CHESS_TO_LEVEL: dict[str, Level] = {v: k for k, v in LEVEL_TO_CHESS.items()}


def resolve_level(profile_level: Level, override: str | None = None) -> Level:
    """Уровень запроса: override (если задан и валиден) иначе уровень профиля.

    Неверный override — ошибка, а не тихое игнорирование (контракт SPEC).
    """
    if override is None:
        return profile_level
    try:
        return Level(override.strip().lower())
    except ValueError:
        from core.errors import AppError

        raise AppError(
            "invalid_level_override",
            f"Недопустимый уровень: {override!r} (novice | intermediate | advanced)",
            422,
        ) from None
