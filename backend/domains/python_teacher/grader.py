"""Батч-прогон решения по assert-тестам (порт идеи батчевого раннера teacher).

Один процесс песочницы на все кейсы: решение ученика + сгенерированный
обвязочный код, каждый тест — try/assert с маркером результата в stdout.
Маркеры солятся per-run (ученик не может напечатать фейковый PASS).
"""

import secrets
from dataclasses import dataclass
from typing import Any

from sandbox.executor import run as sandbox_run
from sandbox.runtime import run_restricted  # noqa: F401 — для будущих батчей в одном процессе

RESTRICTED_ERROR_TYPES = frozenset({"SecurityError", "RestrictedFeatureError"})


@dataclass(frozen=True, slots=True)
class GradeResult:
    verdict: str           # passed | failed | timeout | restricted | error
    passed_tests: int
    total_tests: int
    failed_test: int | None
    stdout_digest: str | None
    duration_ms: int | None
    error: str | None
    sandbox: dict[str, Any]  # сырой результат песочницы


def build_harness(tests: list[str], salt: str) -> str:
    """Обвязка: каждый тест — try/assert с маркером в stdout."""
    pass_mark = f"__CC_{salt}_PASS__"
    fail_mark = f"__CC_{salt}_FAIL__"
    error_mark = f"__CC_{salt}_ERROR__"
    lines: list[str] = []
    for index, test in enumerate(tests):
        lines.append(
            f"try:\n    {test}\n"
            f"    print('{pass_mark}{index}')\n"
            f"except AssertionError as cc_e:\n"
            f"    print('{fail_mark}{index}', cc_e)\n"
            f"except Exception as cc_e:\n"
            f"    print('{error_mark}{index}', type(cc_e))"
        )
    return "\n".join(lines)


async def grade_solution(
    code: str,
    tests: list[str],
    *,
    timeout_s: float,
    memory_limit_mb: int | None = None,
    max_output_chars: int | None = None,
) -> GradeResult:
    """Прогнать решение + тесты в песочнице → вердикт (Design §5.3)."""
    salt = secrets.token_hex(8)
    pass_mark = f"__CC_{salt}_PASS__"
    fail_mark = f"__CC_{salt}_FAIL__"
    error_mark = f"__CC_{salt}_ERROR__"

    header = "\n\n# --- тесты (исполняются в песочнице) ---\n"
    full_code = code + header + build_harness(tests, salt)
    sandbox_result = await sandbox_run(
        full_code,
        timeout_s=timeout_s,
        memory_limit_mb=memory_limit_mb,
        max_output_chars=max_output_chars,
    )
    error_type = sandbox_result.get("error_type")
    if error_type in RESTRICTED_ERROR_TYPES:
        return GradeResult(
            "restricted", 0, len(tests), None, None, None,
            sandbox_result.get("error"), sandbox_result,
        )
    if error_type == "TimeoutError":
        return GradeResult(
            "timeout", 0, len(tests), None, None, None,
            sandbox_result.get("error"), sandbox_result,
        )
    if not sandbox_result["success"]:
        return GradeResult(
            "error", 0, len(tests), None, None, None,
            sandbox_result.get("error"), sandbox_result,
        )

    passed = 0
    failed_test: int | None = None
    student_output: list[str] = []
    for line in sandbox_result["output"].splitlines():
        if line.startswith(pass_mark):
            passed += 1
        elif line.startswith(fail_mark) and failed_test is None:
            failed_test = int(line[len(fail_mark):].split(maxsplit=1)[0])
        elif line.startswith(error_mark) and failed_test is None:
            failed_test = int(line[len(error_mark):].split(maxsplit=1)[0])
        else:
            student_output.append(line)

    digest = "\n".join(student_output)
    if len(digest) > 2000:
        digest = digest[:2000] + "\n… (вывод обрезан)"
    verdict = "passed" if passed == len(tests) else "failed"
    return GradeResult(
        verdict=verdict,
        passed_tests=passed,
        total_tests=len(tests),
        failed_test=failed_test,
        stdout_digest=digest or None,
        duration_ms=int(sandbox_result.get("execution_time", 0) * 1000),
        error=sandbox_result.get("error"),
        sandbox=sandbox_result,
    )
