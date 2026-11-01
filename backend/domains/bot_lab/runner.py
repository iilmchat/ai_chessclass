"""Запуск бота в песочнице: contract choose_move(position)->str (S-17).

Собственный subprocess-раннер (шаблон sandbox/executor): в дочернем
процессе строится SafePosition (python-chess доступен раннеру, ученику —
нет) и вызывается entry-функция; ход валидируется в родителе.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import chess

from core.config import settings
from domains.bot_lab.safe_position import SafePosition
from sandbox.runtime import find_violations

RESULT_MARKER = "CC_BOT_MOVE"
BACKEND_DIR = Path(__file__).resolve().parents[2]

_BOT_RUNNER = (
    "import json, sys\n"
    "import chess\n"
    "from domains.bot_lab.safe_position import SafePosition\n"
    "from sandbox.runtime import run_restricted\n"
    "payload = json.loads(sys.stdin.readline())\n"
    "position = SafePosition(chess.Board(payload['fen']))\n"
    "result = run_restricted(\n"
    "    payload['code'],\n"
    "    memory_limit_mb=payload.get('memory_limit_mb'),\n"
    "    max_output_chars=payload.get('max_output_chars'),\n"
    "    apply_limits=True,\n"
    "    extra_globals={'position': position},\n"
    ")\n"
    "sys.stdout.write(json.dumps(result, ensure_ascii=False))\n"
)


def build_call_code(entry: str) -> str:
    """Хвост: вызов entry(position) + печать маркера с ходом."""
    return (
        f"\n\ncc_move = {entry}(position)\n"
        f"print('{RESULT_MARKER}', cc_move)\n"
    )


def _crash(stderr_tail: str) -> dict[str, Any]:
    return {
        "ok": False, "moveUci": None, "timeMs": 0,
        "error": f"Дочерний процесс песочницы упал: {stderr_tail[-400:]}",
        "errorType": "SandboxCrash", "output": "",
    }


async def run_bot_move(
    code: str,
    entry: str,
    fen: str,
    *,
    timeout_s: float = 1.0,
    memory_limit_mb: int | None = None,
    max_output_chars: int | None = None,
) -> dict[str, Any]:
    """Async-обёртка: subprocess не блокирует event loop."""
    import asyncio

    return await asyncio.to_thread(
        _run_sync, code, entry, fen, timeout_s, memory_limit_mb, max_output_chars
    )


def _run_sync(
    code: str,
    entry: str,
    fen: str,
    timeout_s: float,
    memory_limit_mb: int | None,
    max_output_chars: int | None,
) -> dict[str, Any]:
    """Синхронный запуск (из to_thread или тестов)."""
    # статическая отсечка без spawn
    violations = find_violations(code)
    if violations:
        return {
            "ok": False, "moveUci": None, "timeMs": 0,
            "error": "; ".join(violations),
            "errorType": "SecurityError", "output": "",
        }

    try:
        chess.Board(fen)
    except ValueError as exc:
        return {
            "ok": False, "moveUci": None, "timeMs": 0,
            "error": f"Некорректный FEN: {exc}", "errorType": "InvalidFen",
            "output": "",
        }

    full_code = code + build_call_code(entry)
    payload = json.dumps(
        {
            "fen": fen,
            "code": full_code,
            "memory_limit_mb": (
                memory_limit_mb
                if memory_limit_mb is not None
                else settings.sandbox_memory_limit_mb
            ),
            "max_output_chars": (
                max_output_chars
                if max_output_chars is not None
                else settings.sandbox_max_output_chars
            ),
        },
        ensure_ascii=False,
    )
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _BOT_RUNNER],
            input=payload + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            cwd=str(BACKEND_DIR),
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False, "moveUci": None, "timeMs": int(timeout_s * 1000),
            "error": f"Превышен лимит времени на ход ({timeout_s} с)",
            "errorType": "TimeoutError", "output": "",
        }
    time_ms = int((time.perf_counter() - started) * 1000)

    if completed.returncode != 0:
        return _crash(completed.stderr or "")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return _crash(completed.stderr or completed.stdout or "")
    if not isinstance(result, dict):
        return _crash("раннер вернул не-объект")

    if not result["success"]:
        return {
            "ok": False, "moveUci": None, "timeMs": time_ms,
            "error": result.get("error"),
            "errorType": result.get("error_type"),
            "output": result.get("output") or "",
        }

    move_uci: str | None = None
    student_out: list[str] = []
    for line in (result.get("output") or "").splitlines():
        if line.startswith(RESULT_MARKER):
            parts = line.split(maxsplit=1)
            move_uci = parts[1].strip() if len(parts) > 1 else ""
        else:
            student_out.append(line)

    if not move_uci:
        return {
            "ok": False, "moveUci": None, "timeMs": time_ms,
            "error": "Бот не вернул ход (контракт choose_move(position)->str нарушен)",
            "errorType": "ContractViolation",
            "output": "\n".join(student_out),
        }

    board = chess.Board(fen)
    try:
        move = board.parse_uci(move_uci.strip())
    except ValueError:
        return {
            "ok": False, "moveUci": move_uci, "timeMs": time_ms,
            "error": f"Ход {move_uci!r} нелегален в позиции",
            "errorType": "IllegalMove",
            "output": "\n".join(student_out),
        }

    return {
        "ok": True,
        "moveUci": move.uci(),
        "timeMs": time_ms,
        "error": None,
        "errorType": None,
        "output": "\n".join(student_out),
    }


# SafePosition реэкспорт (используется раннером в дочернем процессе)
__all__ = ["SafePosition", "run_bot_move"]
_ = SafePosition
