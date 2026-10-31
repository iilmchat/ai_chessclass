"""Engine Service (порт app/engine из annotator, §20.2 — почти verbatim).

Анализ позиций через Stockfish 17 (UCI): MultiPV-линии, профили по
шахматному уровню, UCI_Elo для матчей ботов. Движок разрешён только
воркеру («SF — только worker», Design §15.3); API-процесс не ходит в SF.
"""

from engine.errors import (
    EngineError,
    EngineForbiddenError,
    EngineNotFoundError,
    EngineTimeoutError,
)
from engine.models import MATE_CP_BASE, EngineLine
from engine.service import (
    ENGINE_PROFILES,
    EngineProfile,
    EngineService,
    resolve_profile,
)

__all__ = [
    "ENGINE_PROFILES",
    "EngineError",
    "EngineForbiddenError",
    "EngineLine",
    "EngineNotFoundError",
    "EngineProfile",
    "EngineService",
    "EngineTimeoutError",
    "MATE_CP_BASE",
    "resolve_profile",
]
