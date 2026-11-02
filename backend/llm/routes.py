"""Реестр маршрутов v0.1 (Design §8.2): ключ `<domain>.<op>` × level.

Приоритеты моделей — из таблицы §8.2; детальная таблица
«маршрут → модель → параметры» — docs/SPEC.md §6.
"""

from dataclasses import dataclass

from core.errors import AppError
from core.levels import Level


@dataclass(frozen=True, slots=True)
class RouteSpec:
    route: str  # "<domain>.<op>"
    domain: str
    op: str
    purpose: str
    base_tier: str  # модель по умолчанию (novice/intermediate)
    advanced_tier: str | None  # переопределение для advanced (§8.2)


ROUTES: dict[str, RouteSpec] = {
    spec.route: spec
    for spec in (
        RouteSpec("python_teacher.comment", "python_teacher", "comment",
                  "комментарий решения", "L1", None),
        RouteSpec("python_teacher.hint", "python_teacher", "hint",
                  "подсказка", "L1", "L2"),  # L1, L2 для advanced
        RouteSpec("python_teacher.explain_code", "python_teacher", "explain_code",
                  "разбор отправленного кода", "L2", None),
        RouteSpec("chess_lab.insight", "chess_lab", "insight",
                  "текст инсайта позиции", "L2", "L3"),  # L2, L3 для advanced
        RouteSpec("chess_lab.next_moves", "chess_lab", "next_moves",
                  "объяснение топ-3 ходов", "L2", None),
        RouteSpec("chess_lab.blunder", "chess_lab", "blunder",
                  "объяснение плохого хода", "L2", None),
        RouteSpec("chess_lab.commentary", "chess_lab", "commentary",
                  "общий комментарий/беседа", "L1", "L2"),  # L1/L2
        RouteSpec("chess_lab.study", "chess_lab", "study",
                  "условие шахматного этюда", "L1", None),
        RouteSpec("bot_lab.coach", "bot_lab", "coach",
                  "советы по улучшению бота (вне матчей)", "L2", None),
        RouteSpec("anticheat.judge_explain", "anticheat", "judge_explain",
                  "judge-сессия «объясни свой код/ход»", "judge", None),
        RouteSpec("reports.parent_summary", "reports", "parent_summary",
                  "текстовые абзацы для PDF-отчёта", "L1", None),
    )
}


def get_route(route: str) -> RouteSpec:
    spec = ROUTES.get(route)
    if spec is None:
        known = ", ".join(sorted(ROUTES))
        raise AppError("unknown_route", f"Неизвестный маршрут {route!r} (известны: {known})", 500)
    return spec


def resolve_tier(route: str, level: Level) -> str:
    """Тир модели для маршрута и уровня (Design §8.2)."""
    spec = get_route(route)
    if level is Level.ADVANCED and spec.advanced_tier is not None:
        return spec.advanced_tier
    return spec.base_tier
