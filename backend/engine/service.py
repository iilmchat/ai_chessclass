"""Async-обёртка над Stockfish (порт service.py из annotator — почти verbatim).

Почему свой UCI-клиент, а не библиотека `stockfish` (аргументы teacher):

* нужны PV-линии и multipv-ранги — библиотека отдаёт только ходы/оценки;
* нужны жёсткие таймауты поиска (movetime + запас на чтение) и перезапуск
  процесса при зависании;
* нужен неблокирующий event loop: asyncio.create_subprocess_exec напрямую.

Отличия от annotator: UCI_Elo/Threads/Hash (для матчей ботов S-13),
interactive-clamp (movetime ≤ SF_INTERACTIVE_MOVETIME_MS), гвард роли
процесса («SF — только worker», Design §15.3). Кэш/пул/мотивы — S-11+.
"""

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Final

import chess
from pydantic import ValidationError

from core.config import settings
from engine.errors import (
    EngineError,
    EngineForbiddenError,
    EngineNotFoundError,
    EngineTimeoutError,
)
from engine.models import MATE_CP_BASE, EngineLine

__all__ = [
    "ENGINE_PROFILES",
    "EngineProfile",
    "EngineService",
    "resolve_profile",
]

#: Запас времени на чтение ответа поверх movetime (IPC, MultiPV-строки)
_READ_SLACK_S: Final[float] = 4.0
#: Сколько ждать `uciok` при старте
_UCI_STARTUP_S: Final[float] = 15.0
#: Сколько ждать `readyok` после смены опций
_READY_S: Final[float] = 5.0
#: Сколько ждать завершения процесса при закрытии
_SHUTDOWN_S: Final[float] = 2.0

#: диапазон UCI_Elo в SF 17 (ограничение силы для матчей ботов, §8 ladder)
UCI_ELO_MIN: Final[int] = 1320
UCI_ELO_MAX: Final[int] = 3190


@dataclass(frozen=True, slots=True)
class EngineProfile:
    """Параметры поиска для шахматного уровня (порт SPEC.md §2.2 annotator)."""

    depth: int
    multipv: int
    movetime_ms: int


ENGINE_PROFILES: Final[dict[str, EngineProfile]] = {
    "beginner": EngineProfile(depth=12, multipv=1, movetime_ms=200),
    "club": EngineProfile(depth=18, multipv=3, movetime_ms=1000),
    "gm": EngineProfile(depth=28, multipv=5, movetime_ms=5000),
}


def resolve_profile(level: str) -> EngineProfile:
    """Параметры поиска по шахматному уровню (beginner/club/gm)."""
    profile = ENGINE_PROFILES.get(level)
    if profile is None:
        expected = ", ".join(sorted(ENGINE_PROFILES))
        raise EngineError(
            f"Неизвестный уровень {level!r}; ожидается один из: {expected}"
        )
    return profile


def white_cp(line: EngineLine, turn: chess.Color) -> int:
    """Оценка линии с точки зрения белых (UCI отдаёт её за сторону хода)."""
    if line.mate is not None:
        sign = 1 if line.mate > 0 else -1
        cp = sign * (MATE_CP_BASE - 100 * min(abs(line.mate), 99))
    else:
        cp = line.score_cp or 0
    return cp if turn == chess.WHITE else -cp


class EngineService:
    """Сервис анализа позиций через Stockfish; один процесс на сервис.

    Пример::

        async with EngineService() as engine:
            lines = await engine.analyze(fen, "club")
    """

    def __init__(self, *, executable: Path | None = None) -> None:
        if settings.app_role != "worker":
            raise EngineForbiddenError(
                "Stockfish разрешён только воркеру (APP_ROLE=worker, §15.3)"
            )
        self._executable_override = executable
        self._engine: _UciEngine | None = None
        self._lock = asyncio.Lock()

    @property
    def executable_path(self) -> Path:
        if self._executable_override is not None:
            return self._executable_override
        return _resolve_stockfish_path()

    async def __aenter__(self) -> "EngineService":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._engine is not None:
            await self._engine.close()
            self._engine = None

    async def analyze(
        self,
        fen: str,
        level: str = "club",
        *,
        interactive: bool = True,
    ) -> list[EngineLine]:
        """MultiPV-линии позиции по профилю уровня.

        interactive=True — синхронный (интерактивный) вызов: movetime
        ограничен SF_INTERACTIVE_MOVETIME_MS; тяжёлые профили — только
        через воркер-очередь (interactive=False).
        """
        try:
            chess.Board(fen)
        except ValueError as exc:
            raise EngineError(f"Некорректный FEN: {fen!r}: {exc}") from exc
        profile = resolve_profile(level)
        movetime_ms = profile.movetime_ms
        if interactive and movetime_ms > settings.sf_interactive_movetime_ms:
            movetime_ms = settings.sf_interactive_movetime_ms
        async with self._lock:
            engine = await self._ensure_engine()
            engine.configure(
                threads=settings.sf_threads, hash_mb=settings.sf_hash_mb
            )
            return await engine.go(
                fen=fen,
                depth=profile.depth,
                multipv=profile.multipv,
                movetime_ms=movetime_ms,
            )

    async def set_strength(self, elo: int) -> None:
        """UCI_LimitStrength + UCI_Elo (лестница ботов, §8)."""
        if not (UCI_ELO_MIN <= elo <= UCI_ELO_MAX):
            raise EngineError(
                f"UCI_Elo {elo} вне диапазона {UCI_ELO_MIN}..{UCI_ELO_MAX}"
            )
        async with self._lock:
            engine = await self._ensure_engine()
            engine.set_elo(elo)

    async def _ensure_engine(self) -> "_UciEngine":
        if self._engine is not None and self._engine.is_running:
            return self._engine
        engine = _UciEngine(self.executable_path)
        try:
            await engine.start()
        except BaseException:
            await engine.close()
            raise
        self._engine = engine
        return engine


class _UciEngine:
    """Минимальный UCI-клиент: один процесс, один поиск за раз."""

    def __init__(self, executable: Path) -> None:
        self._executable = executable
        self._process: asyncio.subprocess.Process | None = None
        self._name: str | None = None
        self._pending_options: list[str] = []

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def name(self) -> str:
        """Версия движка из UCI-рукопожатия (fallback — stockfish)."""
        return self._name or "stockfish"

    async def start(self) -> None:
        try:
            self._process = await asyncio.create_subprocess_exec(
                str(self._executable),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            self._process = None
            raise EngineNotFoundError(
                f"Не удалось запустить Stockfish ({self._executable}): {exc}"
            ) from exc
        await self._send("uci")
        await self._read_uci_handshake()
        self._configured = False

    async def _read_uci_handshake(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _UCI_STARTUP_S
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise EngineTimeoutError(
                    f"Движок не ответил 'uciok' за {_UCI_STARTUP_S:.1f} с"
                )
            line = await asyncio.wait_for(self._readline(), timeout=remaining)
            if line.startswith("id name "):
                name = line.removeprefix("id name ").strip()
                if name:
                    self._name = name
            if line == "uciok":
                return

    def configure(self, *, threads: int, hash_mb: int) -> None:
        """Отложить setoption Threads/Hash до следующего go (isready там)."""
        self._pending_options = [
            f"setoption name Threads value {max(1, threads)}",
            f"setoption name Hash value {max(1, hash_mb)}",
        ]

    def set_elo(self, elo: int) -> None:
        """Отложить UCI_LimitStrength/UCI_Elo до следующего go."""
        self._pending_options = [
            "setoption name UCI_LimitStrength value true",
            f"setoption name UCI_Elo value {elo}",
        ]

    async def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin is not None and not process.stdin.is_closing():
                process.stdin.write(b"quit\n")
                await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, RuntimeError):
            pass
        try:
            await asyncio.wait_for(process.wait(), timeout=_SHUTDOWN_S)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def go(
        self, *, fen: str, depth: int, multipv: int, movetime_ms: int
    ) -> list[EngineLine]:
        if not self.is_running:
            raise EngineError("Движок не запущен")

        await self._send("ucinewgame")
        await self._send(f"setoption name MultiPV value {multipv}")
        for option in getattr(self, "_pending_options", []):
            await self._send(option)
        self._pending_options = []
        await self._send(f"position fen {fen}")
        await self._send("isready")
        await self._expect("readyok", timeout_s=_READY_S)
        await self._send(f"go depth {depth} movetime {movetime_ms}")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + movetime_ms / 1000 + _READ_SLACK_S
        lines: dict[int, EngineLine] = {}
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError
                line = await asyncio.wait_for(self._readline(), timeout=remaining)
                if line.startswith("bestmove"):
                    break
                if not line.startswith("info "):
                    continue
                parsed = _parse_info_line(line)
                if parsed is not None:
                    lines[parsed.multipv] = parsed
        except TimeoutError as exc:
            # Зависший процесс нельзя «дожать» — убиваем; следующий запрос
            # поднимет новый (EngineService._ensure_engine)
            await self.close()
            raise EngineTimeoutError(
                f"Stockfish не уложился в {movetime_ms} мс (+{_READ_SLACK_S:.0f} с "
                "на чтение) и был перезапущен"
            ) from exc

        if not lines:
            raise EngineError(f"Движок не вернул оценок для позиции {fen!r}")
        return [lines[rank] for rank in sorted(lines)]

    async def _send(self, command: str) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise EngineError("stdin движка закрыт")
        try:
            process.stdin.write((command + "\n").encode("ascii"))
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise EngineError(f"Движок разорвал соединение: {exc}") from exc

    async def _readline(self) -> str:
        process = self._require_process()
        if process.stdout is None:
            raise EngineError("stdout движка закрыт")
        raw = await process.stdout.readline()
        if raw == b"":
            raise EngineError("Stockfish неожиданно завершился (EOF)")
        return raw.decode("utf-8", errors="replace").strip()

    async def _expect(self, token: str, *, timeout_s: float) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise EngineTimeoutError(
                    f"Движок не ответил {token!r} за {timeout_s:.1f} с"
                )
            line = await asyncio.wait_for(self._readline(), timeout=remaining)
            if line == token:
                return

    def _require_process(self) -> asyncio.subprocess.Process:
        if self._process is None:
            raise EngineError("Движок не запущен")
        return self._process


def _resolve_stockfish_path() -> Path:
    """Найти бинарник Stockfish: STOCKFISH_PATH, затем PATH."""
    raw = settings.stockfish_path.strip()
    if raw:
        candidate = Path(raw)
        if candidate.is_file():
            return candidate
    found = shutil.which(raw or "stockfish")
    if found:
        return Path(found)
    raise EngineNotFoundError(
        f"Stockfish не найден: {raw!r}. Укажите STOCKFISH_PATH."
    )


def _parse_info_line(line: str) -> EngineLine | None:
    """Разобрать строку ``info ... multipv K depth D score cp X pv ...``."""
    tokens = line.split()
    if not {"multipv", "depth", "score", "pv"} <= set(tokens):
        return None
    try:
        multipv = int(tokens[tokens.index("multipv") + 1])
        depth = int(tokens[tokens.index("depth") + 1])
        score_at = tokens.index("score")
        score_kind = tokens[score_at + 1]
        score_value = int(tokens[score_at + 2])
        pv = tokens[tokens.index("pv") + 1 :]
    except (IndexError, ValueError):
        return None
    if not pv or score_kind not in {"cp", "mate"}:
        return None

    try:
        return EngineLine(
            multipv=multipv,
            depth=depth,
            score_cp=score_value if score_kind == "cp" else None,
            mate=score_value if score_kind == "mate" else None,
            move_uci=pv[0],
            pv=pv,
        )
    except ValidationError:
        return None
