"""Юнит-тесты единого уровня (Design §4.2, ADR-002) и маппингов доменов."""

import pytest

from core.errors import AppError
from core.levels import (
    CHESS_TO_LEVEL,
    LEVEL_TO_CHESS,
    LEVEL_TO_PYTHON,
    PYTHON_TO_LEVEL,
    Level,
    resolve_level,
)


def test_level_mapping_python():
    assert LEVEL_TO_PYTHON == {
        Level.NOVICE: "basic",
        Level.INTERMEDIATE: "intermediate",
        Level.ADVANCED: "advanced",
    }
    assert PYTHON_TO_LEVEL == {v: k for k, v in LEVEL_TO_PYTHON.items()}


def test_level_mapping_chess():
    assert LEVEL_TO_CHESS == {
        Level.NOVICE: "beginner",
        Level.INTERMEDIATE: "club",
        Level.ADVANCED: "gm",
    }
    assert CHESS_TO_LEVEL == {v: k for k, v in LEVEL_TO_CHESS.items()}


def test_resolve_level_default_is_profile_level():
    assert resolve_level(Level.NOVICE) is Level.NOVICE
    assert resolve_level(Level.ADVANCED) is Level.ADVANCED


def test_resolve_level_override():
    assert resolve_level(Level.NOVICE, "advanced") is Level.ADVANCED
    assert resolve_level(Level.ADVANCED, "  Intermediate ") is Level.INTERMEDIATE


def test_resolve_level_invalid_override_raises():
    with pytest.raises(AppError) as exc_info:
        resolve_level(Level.NOVICE, "guru")
    assert exc_info.value.code == "invalid_level_override"
    assert exc_info.value.status_code == 422
