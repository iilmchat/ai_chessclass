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
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
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
    "    cpu_limit_s=payload.get('cpu_limit_s'),\n"
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


def _cpu_timeout_result(cpu_s: int) -> dict[str, Any]:
    return {
        "success": False,
        "output": "",
        "error": f"Превышен лимит CPU ({cpu_s} с)",
        "error_type": "TimeoutError",
        "violations": [],
    }


@dataclass(frozen=True)
class _NetworkSandbox:
    argv: list[str]
    backend: str
    enforced: bool
    warning: str | None = None


def _bwrap_argv(command: list[str]) -> list[str]:
    """S-97: bwrap с отдельным network namespace и ro-bind зависимостей.

    backend смонтирован read-only: раннер импортирует `sandbox.runtime`,
    но не может писать в код. /tmp — tmpfs; /proc/dev — минимальные.
    """
    backend = str(BACKEND_DIR)
    return [
        "bwrap",
        "--unshare-net",
        "--dev", "/dev",
        "--proc", "/proc",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/usr/local", "/usr/local",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", backend, backend,
        "--tmpfs", "/tmp",
        "--chdir", backend,
        "--die-with-parent",
        *command,
    ]


def _sandbox_command() -> _NetworkSandbox:
    """Выбрать network backend: bwrap → unshare (root) → none + warning."""
    command = [sys.executable, "-c", _RUNNER]
    if not sys.platform.startswith("linux"):
        return _NetworkSandbox(command, "none", False, "сеть: только Linux")
    if not settings.sandbox_network_isolation:
        return _NetworkSandbox(
            command, "none", False, "SANDBOX_NETWORK_ISOLATION=false"
        )
    backend = (settings.sandbox_network_backend or "auto").strip().lower()
    warning: str | None = None
    if backend not in {"auto", "bwrap", "unshare", "none"}:
        warning = f"неизвестный SANDBOX_NETWORK_BACKEND={backend}; auto"
        backend = "auto"
    if backend == "none":
        return _NetworkSandbox(
            command, "none", False, warning or "SANDBOX_NETWORK_BACKEND=none"
        )

    bwrap = shutil.which("bwrap")
    unshare = shutil.which("unshare")
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0

    if backend in {"auto", "bwrap"} and bwrap:
        return _NetworkSandbox(_bwrap_argv(command), "bwrap", True, warning)
    if backend == "bwrap":
        warning = "; ".join(filter(None, [warning, "bwrap не найден"]))

    if backend in {"auto", "unshare"} and unshare and is_root:
        return _NetworkSandbox(
            [unshare, "-n", "--", *command], "unshare", True, warning
        )
    if backend == "unshare" and not is_root:
        warning = "; ".join(filter(None, [warning, "unshare требует root"]))
    if backend == "auto":
        warning = "; ".join(
            filter(None, [warning, "bwrap/unshare недоступны; сеть не изолирована"])
        )
    return _NetworkSandbox(command, "none", False, warning)


def _fallback_sandbox(command: list[str], reason: str) -> _NetworkSandbox:
    """bwrap не смог создать namespace (seccomp/ядро) — fallback."""
    unshare = shutil.which("unshare")
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    warning = f"bwrap fallback: {reason}"
    if unshare and is_root:
        return _NetworkSandbox(
            [unshare, "-n", "--", *command], "unshare", True, warning
        )
    return _NetworkSandbox(
        command, "none", False, warning + "; сеть не изолирована"
    )


def _attach_network(
    result: dict[str, Any],
    sandbox: _NetworkSandbox,
    extra_warning: str | None = None,
) -> dict[str, Any]:
    warnings = [
        item
        for item in (result.get("limits_warning"), sandbox.warning, extra_warning)
        if item
    ]
    result["network_isolation_enforced"] = sandbox.enforced
    result["network_backend"] = sandbox.backend
    result["limits_warning"] = "; ".join(warnings) or None
    return result


def _crash_result(stderr_tail: str) -> dict[str, Any]:
    return {
        "success": False,
        "output": "",
        "error": f"Дочерний процесс песочницы упал: {stderr_tail[-400:]}",
        "error_type": "SandboxCrash",
        "violations": [],
    }


def _run_process(
    argv: list[str], payload: str, timeout_s: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        input=payload + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_s,
        cwd=str(BACKEND_DIR),
    )


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
        return _attach_network(
            {
                "success": False,
                "output": "",
                "error": "; ".join(violations),
                "error_type": "SecurityError",
                "violations": violations,
            },
            _NetworkSandbox([], "none", False),
        )

    payload = json.dumps(
        {
            "code": code,
            "stdin": stdin_text,
            "memory_limit_mb": (
                memory_limit_mb
                if memory_limit_mb is not None
                else settings.sandbox_memory_limit_mb
            ),
            "cpu_limit_s": settings.sandbox_cpu_limit_s,
            "max_output_chars": (
                max_output_chars
                if max_output_chars is not None
                else settings.sandbox_max_output_chars
            ),
        },
        ensure_ascii=False,
    )
    limit = timeout_s if timeout_s is not None else settings.sandbox_timeout_s
    sandbox = _sandbox_command()
    try:
        completed = _run_process(sandbox.argv, payload, limit)
    except subprocess.TimeoutExpired:
        return _attach_network(_timeout_result(limit), sandbox)

    # bwrap может не создать namespace (seccomp/ядро) — не роняем задание,
    # а повторяем через unshare (root) или без сети, с предупреждением.
    stderr = completed.stderr or ""
    if completed.returncode != 0 and sandbox.backend == "bwrap" and "bwrap:" in stderr:
        reason = next(
            (line.strip() for line in stderr.splitlines() if line.strip()),
            "bwrap failed",
        )[:200]
        fallback = _fallback_sandbox([sys.executable, "-c", _RUNNER], reason)
        try:
            completed = _run_process(fallback.argv, payload, limit)
        except subprocess.TimeoutExpired:
            return _attach_network(_timeout_result(limit), fallback)
        sandbox = fallback

    if completed.returncode != 0:
        # RLIMIT_CPU: Linux может прислать SIGXCPU (soft) или SIGKILL (hard,
        # если SIGXCPU проигнорирован/заблокирован) — это timeout, не crash.
        # bwrap возвращает 128+signal (137/152), прямой процесс — -signal.
        sigxcpu = getattr(signal, "SIGXCPU", 24)
        sigkill = getattr(signal, "SIGKILL", 9)
        cpu_codes = {
            -sigxcpu, -sigkill, 128 + sigxcpu, 128 + sigkill
        }
        if completed.returncode in cpu_codes:
            return _attach_network(
                _cpu_timeout_result(settings.sandbox_cpu_limit_s), sandbox
            )
        return _attach_network(
            _crash_result(completed.stderr or ""), sandbox
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return _attach_network(
            _crash_result(completed.stderr or completed.stdout or ""), sandbox
        )
    if not isinstance(result, dict):
        return _attach_network(_crash_result("раннер вернул не-объект"), sandbox)
    return _attach_network(result, sandbox)


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
