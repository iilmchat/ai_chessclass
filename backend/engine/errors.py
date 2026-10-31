"""Ошибки engine-слоя (порт app/errors, классов движка teacher-annotator)."""


class EngineError(Exception):
    """Базовая ошибка движка."""


class EngineNotFoundError(EngineError):
    """Бинарник Stockfish не найден / не запускается."""


class EngineTimeoutError(EngineError):
    """Движок не уложился в бюджет и был перезапущен."""


class EngineForbiddenError(EngineError):
    """Stockfish разрешён только воркеру (Design §15.3 «SF — только worker»)."""
