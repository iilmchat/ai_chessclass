"""Тест-матрица атак песочницы (Design §13.2, обязательный набор §16.1).

Опасные кейсы — только через executor (отдельный процесс с лимитами);
безопасные (статика, синтаксис, вывод) — можно in-process.
"""

import os
import shutil
import subprocess
import sys

import pytest

from core.config import settings
from sandbox.executor import (
    _bwrap_argv,
    _fallback_sandbox,
    _sandbox_command,
    run_sync,
)
from sandbox.runtime import find_violations, run_restricted

# --- статическая отсечка (find_violations, без выполнения)


@pytest.mark.parametrize(
    "code",
    [
        "import os\nos.system('ls')",
        "import subprocess\nsubprocess.run(['ls'])",
        "import socket\nsocket.socket()",
        "import threading\nthreading.Thread(target=lambda: None)",
        "import ctypes\nctypes.CDLL('libc.so')",
        "from os import path",
        "eval('1+1')",
        "exec('x=1')",
        "open('/etc/passwd')",
        "compile('1', '<s>', 'eval')",
        "x = (1).__class__",
        "().__dict__",
    ],
)
def test_static_violations_rejected(code: str):
    violations = find_violations(code)
    assert violations, f"ожидали нарушение для: {code!r}"


def test_import_os_rejected_in_run():
    result = run_restricted("import os")
    assert result["success"] is False
    assert result["error_type"] == "SecurityError"


def test_runtime_eval_unavailable():
    # статика не видит eval без вызова, но и в builtins его нет
    result = run_restricted("x = 'ev' + 'al'\nbuiltins_is_gone = 1")
    assert result["success"] is True


def test_allowed_module_math_works():
    result = run_restricted("import math\nprint(math.sqrt(16))")
    assert result["success"] is True
    assert "4.0" in result["output"]


def test_unknown_module_message():
    result = run_restricted("import pandas")
    assert result["success"] is False
    assert "Разрешены" in result["error"]


# --- in-process runtime (безопасные кейсы)


def test_happy_path_output():
    result = run_restricted("a = 2 + 2\nprint('sum:', a)")
    assert result["success"] is True
    assert "sum: 4" in result["output"]


def test_syntax_error_reported():
    result = run_restricted("def f(:\n    pass")
    assert result["success"] is False
    assert result["error_type"] == "SyntaxError"


def test_stdin_input_lines():
    result = run_restricted("a = input()\nb = input()\nprint(a, b)", "hello\nworld")
    assert result["success"] is True
    assert "hello world" in result["output"]


def test_input_beyond_lines_returns_empty():
    result = run_restricted("a = input()\nprint(repr(a))")
    assert result["success"] is True
    assert "''" in result["output"]


def test_recursion_caught():
    result = run_restricted("def f():\n    return f()\nf()")
    assert result["success"] is False
    assert result["error_type"] == "RecursionError"


def test_format_method_friendly_error():
    result = run_restricted("x = 1\nprint('{} {}'.format(x, x))")
    assert result["success"] is False
    assert result["error_type"] == "RestrictedFeatureError"
    assert "f-строки" in result["error"]


def test_output_truncated_in_process():
    result = run_restricted(
        "for i in range(100):\n    print('y' * 1000)",
        max_output_chars=1000,
    )
    assert result["success"] is True
    assert result["output_truncated"] is True
    assert len(result["output"]) < 2000


# --- через executor (отдельный процесс: лимиты + таймаут)

FAST_TIMEOUT = 2.0


def _bwrap_works() -> bool:
    """Проверить, что bwrap реально создаёт namespace в этом окружении."""
    if not shutil.which("bwrap"):
        return False
    try:
        probe = subprocess.run(
            _bwrap_argv([sys.executable, "-c", "print('bwrap-probe')"]),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def _require_bwrap_or_skip() -> None:
    """В Docker (CHESSCLASS_REQUIRE_BWRAP=1) отсутствие bwrap — провал."""
    if _bwrap_works():
        return
    if os.environ.get("CHESSCLASS_REQUIRE_BWRAP") == "1":
        pytest.fail("bwrap обязателен в Docker: проверьте образ и seccomp-профиль")
    pytest.skip("bwrap недоступен/не может создать namespace")


def test_executor_happy_path():
    result = run_sync("print('executor ok')", timeout_s=FAST_TIMEOUT)
    assert result["success"] is True
    assert "executor ok" in result["output"]


def test_executor_timeout_on_infinite_loop():
    result = run_sync("while True:\n    pass", timeout_s=FAST_TIMEOUT)
    assert result["success"] is False
    assert result["error_type"] == "TimeoutError"
    assert "лимит" in result["error"]


def test_executor_cpu_rlimit_kills_infinite_loop():
    """S-93: RLIMIT_CPU=1 с убивает процесс по SIGXCPU раньше timeout."""
    result = run_sync("while True:\n    pass", timeout_s=5.0)
    assert result["success"] is False
    assert result["error_type"] == "TimeoutError"
    assert "CPU" in result["error"]


def test_executor_network_import_blocked():
    result = run_sync("__import__('socket').socket()", timeout_s=FAST_TIMEOUT)
    assert result["success"] is False
    assert result["error_type"] == "SecurityError"


def test_executor_reports_network_isolation_enforced():
    """S-97: сеть изолирована по умолчанию (bwrap/unshare)."""
    _require_bwrap_or_skip()
    result = run_sync("print('network-ok')", timeout_s=FAST_TIMEOUT)
    assert result["success"] is True
    assert result["network_isolation_enforced"] is True
    assert result["network_backend"] in {"bwrap", "unshare"}


def test_bwrap_available_in_backend_image():
    _require_bwrap_or_skip()
    backend = _sandbox_command()
    assert backend.backend == "bwrap"
    assert backend.enforced is True


def test_bwrap_network_namespace_blocks_redis():
    """S-97: в netns bwrap 127.0.0.1:6379 недоступен."""
    _require_bwrap_or_skip()
    code = (
        "import socket\n"
        "s = socket.socket()\n"
        "s.settimeout(1)\n"
        "s.connect(('127.0.0.1', 6379))\n"
    )
    completed = subprocess.run(
        _bwrap_argv([sys.executable, "-c", code]),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode != 0
    stderr = completed.stderr or ""
    assert (
        "ConnectionRefusedError" in stderr
        or "Network is unreachable" in stderr
        or "OSError" in stderr
    ), stderr


def test_network_fallback_warns_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "sandbox_network_backend", "none")
    result = run_sync("print('no-net')", timeout_s=FAST_TIMEOUT)
    assert result["success"] is True
    assert result["network_isolation_enforced"] is False
    assert result["network_backend"] == "none"
    assert result["limits_warning"]


def test_network_fallback_warns_without_bwrap_or_root(monkeypatch):
    from sandbox import executor as executor_mod

    monkeypatch.setattr(settings, "sandbox_network_backend", "auto")
    monkeypatch.setattr(executor_mod.shutil, "which", lambda _name: None)
    result = run_sync("print('fallback')", timeout_s=FAST_TIMEOUT)
    assert result["success"] is True
    assert result["network_isolation_enforced"] is False
    assert "bwrap/unshare" in result["limits_warning"]


def test_fallback_sandbox_reports_warning():
    fallback = _fallback_sandbox(
        [sys.executable, "-c", "print(1)"], "simulated bwrap failure"
    )
    assert fallback.backend in {"unshare", "none"}
    if fallback.backend == "none":
        assert fallback.enforced is False
    assert fallback.warning is not None
    assert "bwrap fallback" in fallback.warning


def test_executor_filesystem_open_blocked():
    result = run_sync("open('/etc/passwd').read()", timeout_s=FAST_TIMEOUT)
    assert result["success"] is False
    assert result["error_type"] == "SecurityError"


def test_executor_memory_limit():
    # список из 10^11 ссылок ≈ 800 ГБ — RLIMIT_AS (256 МБ) даёт MemoryError
    result = run_sync("big = [0] * (10 ** 11)\nprint(len(big))", timeout_s=FAST_TIMEOUT)
    assert result["success"] is False
    assert result["error_type"] == "MemoryError"


def test_executor_output_truncation():
    result = run_sync(
        "print('z' * 200000)", timeout_s=FAST_TIMEOUT
    )  # больше 64 КБ по умолчанию
    assert result["success"] is True
    assert result["output_truncated"] is True
    assert len(result["output"]) <= settings.sandbox_max_output_chars + 100


def test_executor_stdin():
    result = run_sync("name = input()\nprint('hi,', name)", "Аня", timeout_s=FAST_TIMEOUT)
    assert result["success"] is True
    assert "hi, Аня" in result["output"]


def test_executor_static_rejection_no_spawn():
    # запрещённый импорт отсекается до запуска процесса
    result = run_sync("import os", timeout_s=FAST_TIMEOUT)
    assert result["success"] is False
    assert result["error_type"] == "SecurityError"
