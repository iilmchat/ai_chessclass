"""Чистое ядро песочницы (порт sandbox_runtime.py из teacher, §20.1).

Без зависимостей приложения (ни config, ни БД): модуль используется и в
дочернем процессе-раннере, и тестами напрямую.

Публичное:

* find_violations(code) — статический анализ AST (до выполнения);
* run_restricted(code, stdin, …) — выполнить код, вернуть dict-результат.
"""

import ast
import builtins as builtins_module
import contextlib
import io
import time
from dataclasses import dataclass, field
from typing import Any

from RestrictedPython.compile import compile_restricted

# RP 8.x: `__init__` реэкспортирует имена без `__all__` — импортируем из
# подмодулей явно (порт комментария teacher)
from RestrictedPython.Guards import (
    full_write_guard,
    guarded_iter_unpack_sequence,
    guarded_unpack_sequence,
    safe_builtins,
    safer_getattr,
)
from RestrictedPython.PrintCollector import PrintCollector

from sandbox.limits import apply_cpu_limit, apply_memory_limit, truncate_output

#: Модули, доступные ученику в песочнице
ALLOWED_MODULES: frozenset[str] = frozenset(
    {
        "math",
        "random",
        "datetime",
        "collections",
        "itertools",
        "functools",
        "string",
        "re",
        "statistics",
        "decimal",
        "fractions",
        "json",
    }
)

#: Модули, импорт которых всегда отклоняется (для понятного сообщения)
FORBIDDEN_MODULES: frozenset[str] = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "pathlib",
        "importlib",
        "builtins",
        "ctypes",
        "multiprocessing",
        "threading",
        "sqlite3",
        "http",
        "urllib",
        "requests",
        "pickle",
        "marshal",
        "chess",  # python-chess запрещён ботам (SafePosition вместо него, S-17)
    }
)

#: Функции, вызов которых запрещён. `input` разрешён: читает только stdin.
FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {"eval", "exec", "compile", "open", "__import__", "globals", "locals"}
)


@dataclass(slots=True)
class ExecutionResult:
    """Результат выполнения кода"""

    success: bool
    output: str = ""
    error: str | None = None
    execution_time: float = 0.0
    error_type: str | None = None
    violations: list[str] = field(default_factory=list)
    #: Удалось ли применить лимит памяти
    memory_limit_enforced: bool = False
    #: Был ли вывод обрезан по лимиту
    output_truncated: bool = False


class _OutputCollector:
    """Сборщик `print` для RestrictedPython.

    RP вызывает `_print_` напрямую в одних версиях и `_print_._call_print(...)`
    в других — поддерживаем оба варианта (порт teacher).
    """

    def __init__(self) -> None:
        self._parts: list[str] = []

    def __call__(self, *objects: object, **kwargs: object) -> None:
        self._call_print(*objects, **kwargs)

    def write(self, text: str) -> None:
        self._parts.append(str(text))

    def _call_print(self, *objects: object, **kwargs: object) -> None:
        sep = str(kwargs.get("sep", " "))
        end = str(kwargs.get("end", "\n"))
        self._parts.append(sep.join(str(obj) for obj in objects) + end)

    def getvalue(self) -> str:
        return "".join(self._parts)


def _safe_import(
    name: str,
    globals_: dict[str, Any] | None = None,
    locals_: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
    """Импорт только из белого списка"""
    root = name.split(".")[0]
    if root in FORBIDDEN_MODULES:
        raise ImportError(f"Модуль '{root}' запрещён в песочнице")
    if root not in ALLOWED_MODULES:
        raise ImportError(
            f"Модуль '{root}' недоступен. "
            f"Разрешены: {', '.join(sorted(ALLOWED_MODULES))}"
        )
    return __import__(name, globals_, locals_, fromlist, level)


def _build_builtins() -> dict[str, Any]:
    """Ограниченные builtins: safe_builtins + безопасные встроенные функции"""
    builtins_copy: dict[str, Any] = dict(safe_builtins)
    builtins_copy["__import__"] = _safe_import
    for name in (
        "abs",
        "all",
        "any",
        "bool",
        "chr",
        "dict",
        "divmod",
        "enumerate",
        "float",
        "int",
        "len",
        "list",
        "max",
        "min",
        "ord",
        "pow",
        "range",
        "reversed",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    ):
        builtins_copy[name] = getattr(builtins_module, name)
    return builtins_copy


def _inplace_var(op: str, left: Any, right: Any) -> Any:
    """Guard расширенных присваиваний: RP заменяет `n += 1` на вызов."""
    operations: dict[str, Any] = {
        "+=": lambda a, b: a + b,
        "-=": lambda a, b: a - b,
        "*=": lambda a, b: a * b,
        "/=": lambda a, b: a / b,
        "//=": lambda a, b: a // b,
        "%=": lambda a, b: a % b,
        "**=": lambda a, b: a**b,
        "&=": lambda a, b: a & b,
        "|=": lambda a, b: a | b,
        "^=": lambda a, b: a ^ b,
        "<<=": lambda a, b: a << b,
        ">>=": lambda a, b: a >> b,
    }
    operation = operations.get(op)
    if operation is None:
        raise SyntaxError(f"Неподдерживаемая операция: {op}")
    return operation(left, right)


def _restricted_feature_error(exc: Exception) -> tuple[str, str] | None:
    """Понятное сообщение для ограничений RP 8.x (порт teacher).

    RP 8.x блокирует str.format/format_map (обход песочницы — GHSA-*):
    ученику показываем подсказку про f-строки и %.
    """
    message = str(exc)
    if isinstance(exc, NotImplementedError) and "format" in message.lower():
        return (
            "RestrictedFeatureError",
            "Форматирование через .format()/.format_map() недоступно в "
            "песочнице: используйте f-строки (f\"{x}\") или оператор %.",
        )
    return None


def find_violations(code: str) -> list[str]:
    """Статически найти опасные конструкции (без выполнения)"""
    violations: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    violations.append(f"Импорт запрещённого модуля: {root}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in FORBIDDEN_MODULES:
                violations.append(f"Импорт запрещённого модуля: {root}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                violations.append(f"Вызов запрещённой функции: {node.func.id}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            violations.append(f"Обращение к служебному атрибуту: {node.attr}")
    return violations


def run_restricted(
    code: str,
    stdin_text: str = "",
    *,
    memory_limit_mb: int | None = None,
    cpu_limit_s: int | None = None,
    max_output_chars: int | None = None,
    apply_limits: bool = False,
    extra_globals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Выполнить код в RestrictedPython и вернуть dict-результат.

    Вызывается в дочернем процессе (или тестами напрямую, без apply_limits —
    чтобы не ограничивать сам pytest). `stdin_text` подаётся в `input()`
    построчно; когда строки кончаются, возвращается пустая строка.
    `extra_globals` — безопасные объекты хоста (например SafePosition для
    ботов, S-17); они не могут обойти гварды RestrictedPython.
    """
    violations = find_violations(code)
    if violations:
        return {
            "success": False,
            "output": "",
            "error": "; ".join(violations),
            "error_type": "SecurityError",
            "violations": violations,
        }

    memory_enforced = False
    cpu_enforced = False
    limit_warnings: list[str] = []
    if apply_limits and memory_limit_mb:
        memory_enforced, warning = apply_memory_limit(memory_limit_mb)
        if warning:
            limit_warnings.append(warning)
    if apply_limits and cpu_limit_s:
        cpu_enforced, warning = apply_cpu_limit(cpu_limit_s)
        if warning:
            limit_warnings.append(warning)
    limits_warning = "; ".join(limit_warnings) or None

    stdin_lines = iter(stdin_text.splitlines())

    def _safe_input(prompt: str = "") -> str:
        try:
            return next(stdin_lines)
        except StopIteration:
            return ""

    builtins_for_run = _build_builtins()
    builtins_for_run["input"] = _safe_input

    safe_globals: dict[str, Any] = {
        "__builtins__": builtins_for_run,
        "__name__": "student_script",
        "_print_": PrintCollector,
        "_getattr_": safer_getattr,
        "_getitem_": lambda obj, key: obj[key],
        "_getiter_": iter,
        "_write_": full_write_guard,
        "_inplacevar_": _inplace_var,
        "_unpack_sequence_": guarded_unpack_sequence,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
    }
    if extra_globals:
        safe_globals.update(extra_globals)

    def collected_output() -> str:
        printer = safe_globals.get("_print")
        if callable(printer):
            try:
                return str(printer())
            except Exception:  # noqa: BLE001 — не ломаем отчёт о результате
                return ""
        return ""

    started = time.perf_counter()
    try:
        byte_code = compile_restricted(code, "<student_code>", "exec")
    except SyntaxError as exc:
        return {
            "success": False,
            "output": "",
            "error": f"{exc.msg} (строка {exc.lineno})",
            "error_type": "SyntaxError",
            "violations": violations,
            "memory_limit_enforced": memory_enforced,
            "cpu_limit_enforced": cpu_enforced,
            "network_isolation_enforced": False,
            "network_backend": "none",
            "limits_warning": limits_warning,
        }
    except Exception as exc:  # noqa: BLE001 — RP может бросить своё
        restricted = _restricted_feature_error(exc)
        return {
            "success": False,
            "output": "",
            "error": restricted[1] if restricted else str(exc),
            "error_type": restricted[0] if restricted else type(exc).__name__,
            "violations": violations,
            "memory_limit_enforced": memory_enforced,
            "cpu_limit_enforced": cpu_enforced,
            "network_isolation_enforced": False,
            "network_backend": "none",
            "limits_warning": limits_warning,
        }

    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            exec(byte_code, safe_globals)  # noqa: S102 — код ограничен RP
    except Exception as exc:  # noqa: BLE001 — любая ошибка ученика
        output, truncated = truncate_output(
            collected_output() + buffer.getvalue(), max_output_chars
        )
        restricted = _restricted_feature_error(exc)
        return {
            "success": False,
            "output": output,
            "error": restricted[1] if restricted else f"{type(exc).__name__}: {exc}",
            "error_type": restricted[0] if restricted else type(exc).__name__,
            "execution_time": time.perf_counter() - started,
            "violations": violations,
            "memory_limit_enforced": memory_enforced,
            "cpu_limit_enforced": cpu_enforced,
            "network_isolation_enforced": False,
            "network_backend": "none",
            "output_truncated": truncated,
            "limits_warning": limits_warning,
        }

    output, truncated = truncate_output(
        collected_output() + buffer.getvalue(), max_output_chars
    )
    return {
        "success": True,
        "output": output,
        "error": None,
        "error_type": None,
        "execution_time": time.perf_counter() - started,
        "violations": violations,
        "memory_limit_enforced": memory_enforced,
        "cpu_limit_enforced": cpu_enforced,
        "network_isolation_enforced": False,
        "network_backend": "none",
        "output_truncated": truncated,
        "limits_warning": limits_warning,
    }
