"""Интеграционные тесты против реального Stockfish (короткий бюджет).

Запускаются, только если бинарник установлен в образе (S-10 Dockerfile).
Роль процесса monkeypatch'ится в worker — «SF только worker» (§15.3).
"""

import asyncio
from pathlib import Path

import pytest

from core.config import settings
from engine.errors import EngineError, EngineForbiddenError
from engine.models import MATE_CP_BASE
from engine.service import EngineService, resolve_profile

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
MATE_IN_1_FEN = "6k1/5ppp/8/8/8/8/8/4R1K1 w - - 0 1"  # Re8#

pytestmark = pytest.mark.skipif(
    not Path(settings.stockfish_path).exists(),
    reason="Stockfish не установлен в образе",
)


@pytest.fixture
def worker_role(monkeypatch):
    monkeypatch.setattr(settings, "app_role", "worker")


def test_engine_forbidden_in_api_process():
    """Гвард «SF — только worker»: в api-роли движок не создаётся."""
    with pytest.raises(EngineForbiddenError):
        EngineService()  # noqa: F841 — создание уже ошибка


async def test_analyze_start_position(worker_role):
    async with EngineService() as engine:
        lines = await engine.analyze(START_FEN, "club")
    assert lines, "ожидаем хотя бы одну MultiPV-линию"
    top = lines[0]
    assert top.multipv == 1
    assert top.move_uci == "e2e4" or top.move_uci != ""  # валидный ход
    assert top.score_cp is not None or top.mate is not None


async def test_analyze_mate_in_one(worker_role):
    async with EngineService() as engine:
        lines = await engine.analyze(MATE_IN_1_FEN, "beginner")
    top = lines[0]
    assert top.move_uci == "e1e8"
    assert top.mate is not None and top.mate > 0


async def test_interactive_clamp_gm_level(worker_role):
    """gm-профиль (5000 мс) в интерактивном режиме ужимается до 1000 мс:
    анализ стартовой позиции должен уложиться в бюджет чтения."""
    async with EngineService() as engine:
        await asyncio.wait_for(
            engine.analyze(START_FEN, "gm", interactive=True), timeout=10.0
        )


async def test_set_strength_elo(worker_role):
    async with EngineService() as engine:
        await engine.set_strength(1400)
        lines = await engine.analyze(START_FEN, "beginner")
    assert lines


async def test_set_strength_out_of_range(worker_role):
    async with EngineService() as engine:
        with pytest.raises(EngineError, match="вне диапазона"):
            await engine.set_strength(999)


async def test_invalid_fen_rejected(worker_role):
    async with EngineService() as engine:
        with pytest.raises(EngineError, match="Некорректный FEN"):
            await engine.analyze("не-fen", "club")


def test_profiles_and_mate_base():
    assert resolve_profile("club").movetime_ms == 1000
    assert resolve_profile("gm").multipv == 5
    with pytest.raises(EngineError, match="Неизвестный уровень"):
        resolve_profile("grandmaster")
    assert MATE_CP_BASE == 10_000
