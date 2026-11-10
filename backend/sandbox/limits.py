"""Ограничения ресурсов песочницы (порт sandbox_limits.py из teacher).

Лимит памяти ставится внутри дочернего интерпретатора (не в родителе):
- POSIX: `resource.setrlimit(RLIMIT_AS)`;
- Windows: Job Object с `JOB_OBJECT_LIMIT_PROCESS_MEMORY` (процесс назначает
  себя в job сам — гонок с запуском кода нет).
"""

import sys
from typing import Any

#: Сколько символов stdout/stderr максимум отдаём клиенту (64 КБ, §13.2)
DEFAULT_MAX_OUTPUT_CHARS = 65_536

OUTPUT_TRUNCATED_NOTE = "\n… вывод обрезан: превышен лимит {limit} символов"

#: Флаг Job Object: ограничить committed memory процесса
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

#: Держим handle job до конца жизни процесса, иначе job уничтожается
_WINDOWS_JOB: Any = None


def truncate_output(text: str, max_chars: int | None) -> tuple[str, bool]:
    """Обрезать вывод по лимиту; вернуть (текст, был_ли_обрезан)."""
    limit = max_chars if max_chars and max_chars > 0 else DEFAULT_MAX_OUTPUT_CHARS
    if len(text) <= limit:
        return text, False
    return (
        text[:limit] + OUTPUT_TRUNCATED_NOTE.format(limit=limit),
        True,
    )


def apply_cpu_limit(limit_s: int) -> tuple[bool, str | None]:
    """S-93: RLIMIT_CPU на POSIX (SIGXCPU при превышении)."""
    if limit_s <= 0:
        return False, "лимит CPU отключён"
    if sys.platform == "win32":
        return False, "RLIMIT_CPU недоступен на Windows"
    try:
        import resource
    except ImportError as exc:  # pragma: no cover
        return False, f"resource недоступен: {exc}"
    resource_any: Any = resource
    try:
        _, hard = resource_any.getrlimit(resource_any.RLIMIT_CPU)
        new_hard = (
            limit_s
            if hard == resource_any.RLIM_INFINITY
            else min(int(hard), limit_s)
        )
        resource_any.setrlimit(resource_any.RLIMIT_CPU, (limit_s, new_hard))
    except (OSError, ValueError) as exc:
        return False, f"setrlimit(RLIMIT_CPU): {exc}"
    return True, None


def apply_memory_limit(limit_mb: int) -> tuple[bool, str | None]:
    """Применить лимит памяти к текущему процессу.

    Возвращает `(enforced, reason)`: reason заполняется, если лимит применить
    не удалось (тогда песочница продолжает работать с таймаутом).
    """
    if limit_mb <= 0:
        return False, "лимит памяти отключён (SANDBOX_MEMORY_LIMIT_MB=0)"
    limit_bytes = limit_mb * 1024 * 1024
    if sys.platform == "win32":
        return _apply_windows_memory_limit(limit_bytes)
    return _apply_posix_memory_limit(limit_bytes)


def _apply_posix_memory_limit(limit_bytes: int) -> tuple[bool, str | None]:
    """RLIMIT_AS на Linux/macOS"""
    try:
        import resource
    except ImportError as exc:  # pragma: no cover — экзотическая платформа
        return False, f"resource недоступен: {exc}"

    # mypy видит resource только с атрибутами текущей платформы, поэтому
    # работаем через Any — вызов всё равно только на POSIX
    resource_any: Any = resource
    try:
        _, hard = resource_any.getrlimit(resource_any.RLIMIT_AS)
        new_hard = (
            limit_bytes
            if hard == resource_any.RLIM_INFINITY
            else min(int(hard), limit_bytes)
        )
        resource_any.setrlimit(resource_any.RLIMIT_AS, (new_hard, new_hard))
    except (OSError, ValueError) as exc:
        return False, f"setrlimit(RLIMIT_AS): {exc}"
    return True, None


def _apply_windows_memory_limit(limit_bytes: int) -> tuple[bool, str | None]:
    """Job Object с лимитом памяти процесса (Windows; порт teacher)."""
    global _WINDOWS_JOB
    if sys.platform != "win32":  # pragma: no cover — защита от прямого вызова
        return False, "Job Object доступен только на Windows"

    import ctypes
    from ctypes import wintypes

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", wintypes.PVOID),
            ("PriorityClass", wintypes.DWORD),
            ("ProcessIDLimit", wintypes.DWORD),
            ("Reserved", wintypes.DWORD * 4),
        ]

    class _IOCounters(ctypes.Structure):
        _fields_ = [(f"ReadOperationCount{i}", ctypes.c_int64) for i in range(2)] + [
            (f"WriteOperationCount{i}", ctypes.c_int64) for i in range(2)
        ] + [
            (f"OtherOperationCount{i}", ctypes.c_int64) for i in range(2)
        ] + [
            ("ReadTransferCount", ctypes.c_int64),
            ("WriteTransferCount", ctypes.c_int64),
            ("OtherTransferCount", ctypes.c_int64),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IOCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        return False, "CreateJobObjectW не удался"

    info = _ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.ProcessMemoryLimit = limit_bytes
    if not kernel32.SetInformationJobObject(
        handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        return False, "SetInformationJobObject не удался"
    current = kernel32.GetCurrentProcess()
    if not kernel32.AssignProcessToJobObject(handle, current):
        return False, "AssignProcessToJobObject не удался"
    _WINDOWS_JOB = handle  # noqa: F841 — держим handle живым
    return True, None
