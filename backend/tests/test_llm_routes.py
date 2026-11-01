"""Юнит-тесты реестра маршрутов и resolve по уровню (Design §8.2)."""

import pytest

from core.errors import AppError
from core.levels import Level
from llm.models_registry import MODELS, TIERS
from llm.routes import ROUTES, get_route, resolve_tier


def test_registry_has_all_v01_routes():
    expected = {
        "python_teacher.comment", "python_teacher.hint", "python_teacher.explain_code",
        "chess_lab.insight", "chess_lab.next_moves", "chess_lab.blunder",
        "chess_lab.commentary", "bot_lab.coach", "anticheat.judge_explain",
        "reports.parent_summary",
    }
    assert set(ROUTES) == expected


def test_models_registry_tiers_and_prices():
    assert set(MODELS) == set(TIERS)
    assert MODELS["L1"].price_in is not None and MODELS["L1"].price_out is not None
    # S-31: цены judge/L3-alt взяты из каталога RouterAI
    assert MODELS["judge"].price_in is not None
    assert MODELS["L3_alt"].price_in is not None


def test_resolve_tier_by_level():
    # базовые приоритеты (Design §8.2)
    assert resolve_tier("python_teacher.comment", Level.NOVICE) == "L1"
    assert resolve_tier("python_teacher.explain_code", Level.INTERMEDIATE) == "L2"
    # advanced-переопределения
    assert resolve_tier("python_teacher.hint", Level.ADVANCED) == "L2"
    assert resolve_tier("python_teacher.hint", Level.NOVICE) == "L1"
    assert resolve_tier("chess_lab.insight", Level.ADVANCED) == "L3"
    assert resolve_tier("chess_lab.insight", Level.INTERMEDIATE) == "L2"
    # judge-маршрут не зависит от уровня
    assert resolve_tier("anticheat.judge_explain", Level.ADVANCED) == "judge"


def test_unknown_route_raises():
    with pytest.raises(AppError) as exc_info:
        get_route("chess_lab.teleport")
    assert exc_info.value.code == "unknown_route"
