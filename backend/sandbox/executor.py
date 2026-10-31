"""Executor: выполнение кода ученика в отдельном интерпретаторе (S-07).

API-процесс никогда не `exec`-ит ученический код (Design §13.2): каждый
запуск — свежий `python -c <раннер>` с JSON-протоколом по stdin/stdout,
per-run timeout (kill) и лимитом памяти внутри дочернего процесса
(RLIMIT_AS/Job Object). Пул/батч/контейнерный режим — S-08+ (порт teacher).

Почему subprocess, а не multiprocessing (порт аргумента teacher): на Windows
spawn перезапускает `__main__` и конфликтует с uvicorn; отдельный
интерпретатор изолирован полностью и от `__main__` не зависит.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.config import settings
from sandbox.runtime import find_violations

#: Каталог backend — дочерний интерпретатор импортирует `sandbox` отсюда
BACKEND_DIR = Path(__file__).resolve().parents[1]

#: Раннер дочернего процесса: читает JSON-строку из stdin, пишет JSON-результат
_RUNNER = (
    "import json, sys\n"
    "from sandbox.runtime import run_restricted\n"
    "payload = json.loads(sys.stdin.readline())\n"
    "result = run_restricted(\n"
    "    payload['code'],\n"
    "    payload.get('stdin', ''),\n"
    "    memory_limit_mb=payload.get('memory_limit_mb'),\n"
    "    max_output_chars=payload.get('max_output_chars'),\n"
    "    apply_limits=True,\n"
    ")\n"
    "sys.stdout.write(json.dumps(result, ensure_ascii=False))\n"
)


def _timeout_result(timeout_s: float) -> dict[str, Any]:
    return {
        "success": False,
        "output": "",
        "error": f"Превышен лимит времени выполнения ({timeout_s} с)",
        "error_type": "TimeoutError",
        "violations": [],
    }


def _crash_result(stderr_tail: str) -> dict[str, Any]:
    return {
        "success": False,
        "output": "",
        "error": f"Дочерний процесс песочницы упал: {stderr_tail[-400:]}",
        "error_type": "SandboxCrash",
        "violations": [],
    }


def run_sync(
    code: str,
    stdin_text: str = "",
    *,
    timeout_s: float | None = None,
    memory_limit_mb: int | None = None,
    max_output_chars: int | None = None,
) -> dict[str, Any]:
    """Синхронный запуск в дочернем интерпретаторе (вызывать из потока)."""
    # Быстрая статическая отсечка без spawn (violations → SecurityError)
    violations = find_violations(code)
    if violations:
        return {
            "success": False,
            "output": "",
            "error": "; ".join(violations),
            "error_type": "SecurityError",
            "violations": violations,
        }

    payload = json.dumps(
        {
            "code": code,
            "stdin": stdin_text,
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
    limit = timeout_s if timeout_s is not None else settings.sandbox_timeout_s
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _RUNNER],
            input=payload + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=limit,
            cwd=str(BACKEND_DIR),
        )
    except subprocess.TimeoutExpired:
        return _timeout_result(limit)

    if completed.returncode != 0:
        return _crash_result(completed.stderr or "")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return _crash_result(completed.stderr or completed.stdout or "")
    if not isinstance(result, dict):
        return _crash_result("раннер вернул не-объект")
    return result


async def run(
    code: str,
    stdin_text: str = "",
    *,
    timeout_s: float | None = None,
    memory_limit_mb: int | None = None,
    max_output_chars: int | None = None,
) -> dict[str, Any]:
    """Async-обёртка: subprocess не блокирует event loop."""
    import asyncio

    return await asyncio.to_thread(
        run_sync,
        code,
        stdin_text,
        timeout_s=timeout_s,
        memory_limit_mb=memory_limit_mb,
        max_output_chars=max_output_chars,
    )
