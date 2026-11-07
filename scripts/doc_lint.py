#!/usr/bin/env python3
"""S-60: doc-lint gate — документы не должны расходиться с фактом.

Проверки (каждая независима, ошибки агрегируются, на первой не останавливаемся):
  A) согласованность версий: backend/pyproject.toml, frontend/package.json,
     backend/app/__init__.py (__version__), backend/app/main.py (FastAPI version),
     default IMAGE_TAG в docker-compose.prod.yml / docker-compose.staging.yml;
  B) alembic-граф: head (revision, не встречающийся в down_revision) и число
     миграций = строке README «Alembic head **<head>** (<count>)»;
  C) счётчики тестов в README: backend vs `pytest --collect-only` (--tests-count
     auto|N), frontend vs `it(` в frontend/src/**/*.test.ts(x), e2e vs `test(`
     в frontend/e2e/*.spec.ts;
  D) ровно один активный план в docs/README.md (TODO_V0.7.1.md), архивные планы;
  E) стрейл-маркеры только в активных доках, версия в шапке Design.md,
     release-notes текущей версии;
  F) активный этап и прогресс в TODO_V0.7.1.md.

CLI:
    python scripts/doc_lint.py [--root PATH] [--tests-count auto|N]
                               [--skip-tests-count]

Вывод: одна строка на проверку (`[ok]`/`[FAIL]`) и итог
`doc-lint: N checks, M failed`. Код возврата: 0 — всё ok; 1 — есть FAIL.
Только stdlib (Python 3.12), без сети и БД.
"""

import argparse
import ast
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path

#: Активные документы: устаревшие маркеры допустимы только в архивах/отчётах.
ACTIVE_DOCS: tuple[str, ...] = (
    "README.md",
    "Design.md",
    "TODO_V0.7.md",
    "TODO_V0.7.1.md",
    "docs/README.md",
    "docs/release-notes-v0.3.0.md",
    "docs/release-notes-v0.7.0.md",
    "docs/runbooks/llm-gateway.md",
    "docs/runbooks/staging.md",
    "docs/runbooks/operations.md",
    "docs/runbooks/release-v0.3.0.md",
)

#: Маркеры прошлых этапов, которых не должно быть в активных доках.
FORBIDDEN_MARKERS: tuple[str, ...] = (
    "16/16",
    "174 passed",
    "0021_tournaments",
    "v0.2.0 Draft",
)

README_COUNT_PATTERNS: dict[str, re.Pattern[str]] = {
    "backend": re.compile(r"Тесты backend\s*\|\s*\*\*(\d+) passed\*\*"),
    "frontend": re.compile(r"Тесты frontend\s*\|\s*\*\*(\d+) passed\*\*"),
    "e2e": re.compile(r"UI-e2e\s*\|\s*\*\*(\d+) passed\*\*"),
}

README_ALEMBIC_RE = re.compile(
    r"Alembic head \*\*(?P<head>[0-9a-z_]+)\*\* \((?P<count>\d+)\)"
)

#: Ожидаемый прогресс активного плана v0.7.1: S-86 закрыт;
#: S-87…S-89 впереди.
EXPECTED_PROGRESS: tuple[int, int] = (1, 4)

CollectError = str


def read_text(path: Path) -> str:
    """Прочитать UTF-8-текст (ожидаемая кодировка всех доков)."""
    return path.read_text(encoding="utf-8")


def _parse_version(raw: str) -> str | None:
    """Выделить X.Y.Z из сырого значения (toml/json/regex-фрагмент)."""
    match = re.search(r"(\d+\.\d+\.\d+)", raw)
    return match.group(1) if match else None


# --- A: версии


def _pyproject_version(path: Path) -> str:
    data = tomllib.loads(read_text(path))
    return _parse_version(str(data["project"]["version"])) or ""


def _package_json_version(path: Path) -> str:
    data = json.loads(read_text(path))
    return _parse_version(str(data["version"])) or ""


def _regex_version(path: Path, pattern: re.Pattern[str]) -> str:
    match = pattern.search(read_text(path))
    return (_parse_version(match.group(1)) if match else "") or ""


def _compose_version(path: Path) -> str:
    """Default IMAGE_TAG; суффикс варианта образа (``-staging``) отбрасывается."""
    defaults = re.findall(r"\$\{IMAGE_TAG:-([^}]+)\}", read_text(path))
    bases = {item.split("-")[0] for item in defaults}
    return bases.pop() if len(bases) == 1 else ""


def _collect_versions(root: Path) -> dict[str, str]:
    """Версия из каждого источника; '' — источник не читается/не разобран."""
    loaders: dict[str, Callable[[], str]] = {
        "backend/pyproject.toml": lambda: _pyproject_version(
            root / "backend/pyproject.toml"
        ),
        "frontend/package.json": lambda: _package_json_version(
            root / "frontend/package.json"
        ),
        "backend/app/__init__.py": lambda: _regex_version(
            root / "backend/app/__init__.py",
            re.compile(r"__version__\s*=\s*[\"']([^\"']+)[\"']"),
        ),
        "backend/app/main.py": lambda: _regex_version(
            root / "backend/app/main.py", re.compile(r"\bversion=\"([^\"]+)\"")
        ),
        "docker-compose.prod.yml": lambda: _compose_version(
            root / "docker-compose.prod.yml"
        ),
        "docker-compose.staging.yml": lambda: _compose_version(
            root / "docker-compose.staging.yml"
        ),
    }
    versions: dict[str, str] = {}
    for source, loader in loaders.items():
        try:
            versions[source] = loader()
        except (OSError, ValueError, KeyError, TypeError):
            versions[source] = ""
    return versions


def _check_versions(root: Path) -> list[str]:
    versions = _collect_versions(root)
    errors = [
        f"A: {source}: не удалось извлечь версию"
        for source, value in versions.items()
        if not value
    ]
    present = sorted({value for value in versions.values() if value})
    if len(present) > 1:
        details = ", ".join(f"{source}={value}" for source, value in versions.items())
        errors.append(f"A: версии расходятся: {details}")
    return errors


# --- B: миграции


def _assignment_value(tree: ast.Module, name: str) -> str | None:
    """Строковое значение module-level `name = "..."` / `name: str = "..."`."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: Sequence[ast.expr] = node.targets
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in targets
            ):
                return _const_str(node.value)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name:
                return _const_str(node.value)
    return None


def _const_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _alembic_graph(root: Path) -> tuple[str, int]:
    """(head, files): head — единственный revision, отсутствующий в down_revision."""
    versions_dir = root / "backend/migrations/versions"
    files = sorted(versions_dir.glob("*.py"))
    revisions: list[str] = []
    down_revisions: set[str] = set()
    for path in files:
        tree = ast.parse(read_text(path), filename=str(path))
        revision = _assignment_value(tree, "revision")
        down = _assignment_value(tree, "down_revision")
        if revision:
            revisions.append(revision)
        if down:
            down_revisions.add(down)
    heads = [revision for revision in revisions if revision not in down_revisions]
    head = heads[0] if len(heads) == 1 else ""
    return head, len(files)


def _check_migrations(root: Path) -> list[str]:
    try:
        head, count = _alembic_graph(root)
    except (OSError, SyntaxError) as exc:
        return [f"B: не удалось разобрать миграции: {exc}"]
    errors: list[str] = []
    if not head:
        errors.append(
            "B: не найден единственный alembic head (проверьте revision/down_revision)"
        )
    try:
        readme = read_text(root / "README.md")
    except OSError as exc:
        return errors + [f"B: README.md не читается: {exc}"]
    match = README_ALEMBIC_RE.search(readme)
    if match is None:
        errors.append("B: в README нет строки 'Alembic head **<head>** (<count>)'")
        return errors
    if head and match.group("head") != head:
        errors.append(f"B: README head={match.group('head')}, факт={head}")
    if int(match.group("count")) != count:
        errors.append(f"B: README count={match.group('count')}, факт={count}")
    return errors


# --- C: счётчики тестов


def _readme_counts(text: str) -> dict[str, int]:
    """Счётчики из таблицы статуса README: backend/frontend/e2e (если найдены)."""
    counts: dict[str, int] = {}
    for key, pattern in README_COUNT_PATTERNS.items():
        match = pattern.search(text)
        if match:
            counts[key] = int(match.group(1))
    return counts


def _count_matches(paths: Sequence[Path], pattern: re.Pattern[str]) -> int:
    return sum(len(pattern.findall(read_text(path))) for path in paths)


def _count_frontend_tests(root: Path) -> int:
    frontend = root / "frontend"
    paths = [
        *frontend.glob("src/**/*.test.ts"),
        *frontend.glob("src/**/*.test.tsx"),
    ]
    return _count_matches(sorted(paths), re.compile(r"^\s*it\(", re.MULTILINE))


def _count_e2e_tests(root: Path) -> int:
    paths = sorted((root / "frontend/e2e").glob("*.spec.ts"))
    return _count_matches(paths, re.compile(r"^\s*test\(", re.MULTILINE))


def _collect_backend_tests(backend_dir: Path) -> tuple[int | None, CollectError]:
    """pytest --collect-only -q: (collected|None, текст ошибки)."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"pytest --collect-only: {type(exc).__name__}: {exc}"
    output = (proc.stdout or "") + (proc.stderr or "")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in reversed(lines):
        match = re.search(r"(\d+) tests? collected", line)
        if match:
            return int(match.group(1)), ""
    tail = " | ".join(lines[-3:])[:400]
    return None, (
        f"pytest --collect-only: rc={proc.returncode}, хвост вывода: {tail!r}"
    )


def _check_counts(
    root: Path,
    tests_count: int | None,
    skip_tests: bool,
    collection_error: CollectError = "",
) -> list[str]:
    try:
        readme = read_text(root / "README.md")
    except OSError as exc:
        return [f"C: README.md не читается: {exc}"]
    counts = _readme_counts(readme)
    errors: list[str] = []

    if skip_tests:
        pass  # backend-счётчик пропущен явно (--skip-tests-count)
    else:
        expected = counts.get("backend")
        if expected is None:
            errors.append("C: README: нет строки 'Тесты backend | **N passed**'")
        elif tests_count is None:
            detail = f" ({collection_error})" if collection_error else ""
            errors.append(f"C: не удалось определить число backend-тестов{detail}")
        elif expected != tests_count:
            errors.append(
                f"C: backend: README={expected}, pytest collect={tests_count}"
                " — обновите README"
            )

    for key, actual, label in (
        ("frontend", _count_frontend_tests(root), "it() в frontend/src"),
        ("e2e", _count_e2e_tests(root), "test() в frontend/e2e"),
    ):
        expected = counts.get(key)
        if expected is None:
            errors.append(f"C: README: нет строки для '{key}'")
        elif expected != actual:
            errors.append(
                f"C: {key}: README={expected}, факт={actual} ({label})"
                " — обновите README"
            )
    return errors


# --- D: активный план


def _active_plan_rows(text: str) -> list[str]:
    """Строки таблицы, где «активный» — значение ячейки статуса (не текст описания)."""
    rows: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if any(re.fullmatch(r"(?:✅\s*)?активный", cell) for cell in cells):
            rows.append(stripped)
    return rows


def _check_active_plan(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        docs_readme = read_text(root / "docs/README.md")
    except OSError as exc:
        return [f"D: docs/README.md не читается: {exc}"]
    active_rows = _active_plan_rows(docs_readme)
    if len(active_rows) != 1:
        errors.append(
            f"D: в docs/README.md строк со статусом 'активный' —"
            f" {len(active_rows)} (нужна ровно одна)"
        )
    elif "TODO_V0.7.1.md" not in active_rows[0]:
        errors.append(
            "D: активный план — не TODO_V0.7.1.md: " + active_rows[0].strip()
        )
    for name in (
        "TODO_V0.7.1.md",
        "TODO_V0.7.md",
        "TODO_V0.6.md",
        "TODO_V0.1.md",
        "TODO_V0.2.md",
    ):
        if not (root / name).is_file():
            errors.append(f"D: отсутствует {name}")
    for name in (
        "TODO_V0.3.md",
        "TODO_V0.4.md",
        "TODO_V0.5.md",
        "TODO_V0.6.md",
        "TODO_V0.7.md",
    ):
        try:
            header = "\n".join(read_text(root / name).splitlines()[:10])
        except OSError:
            errors.append(f"D: {name} не читается")
            continue
        if "✅" not in header and "завершён" not in header:
            errors.append(f"D: {name}: в шапке нет отметки о завершении")
    return errors


# --- E: стрейл-маркеры и версия в шапке Design


def _stale_hits(text: str, name: str = "text") -> list[str]:
    """Запрещённые маркеры прошлых этапов в тексте активного документа."""
    return [
        f"E: {name}: запрещённый стрейл-маркер {marker!r}"
        for marker in FORBIDDEN_MARKERS
        if marker in text
    ]


def _check_no_stale(root: Path, rel_paths: Sequence[str]) -> list[str]:
    """Проверить активные доки; отсутствие файла из списка — тоже ошибка."""
    errors: list[str] = []
    for rel in rel_paths:
        try:
            text = read_text(root / rel)
        except OSError:
            errors.append(f"E: активный документ отсутствует: {rel}")
            continue
        errors.extend(_stale_hits(text, rel))
    return errors


def _check_stale(root: Path) -> list[str]:
    errors = _check_no_stale(root, ACTIVE_DOCS)
    version = _collect_versions(root).get("backend/pyproject.toml", "")
    try:
        header_lines = read_text(root / "Design.md").splitlines()[:10]
    except OSError:
        return errors + ["E: Design.md не читается"]
    header = next(
        (line for line in header_lines if "**Версия:**" in line), ""
    )
    if not header:
        errors.append("E: Design.md: в шапке нет строки '**Версия:** v... ·'")
    else:
        if version and re.search(
            rf"\*\*Версия:\*\*\s*v{re.escape(version)}\s*·", header
        ) is None:
            errors.append(
                f"E: Design.md: шапка не '**Версия:** v{version} ·' —"
                f" {header.strip()}"
            )
        if "Draft" in header:
            errors.append("E: Design.md: в шапке 'Draft'")
    if version and not (root / f"docs/release-notes-v{version}.md").is_file():
        errors.append(f"E: нет docs/release-notes-v{version}.md")
    return errors


# --- F: прогресс активного плана


def _check_todo_progress(root: Path) -> list[str]:
    try:
        text = read_text(root / "TODO_V0.7.1.md")
    except OSError as exc:
        return [f"F: TODO_V0.7.1.md не читается: {exc}"]
    errors: list[str] = []
    if "v0.7.1" not in text:
        errors.append("F: TODO_V0.7.1.md не упоминает активный этап v0.7.1")
    if "Прогресс:" not in text:
        errors.append("F: TODO_V0.7.1.md: нет строки 'Прогресс:'")
    summary = re.search(r"\*\*Сводно:\*\*\s*(\d+)\s+спринт", text)
    progress = re.search(r"\*\*Прогресс:\s*(\d+)/(\d+)", text)
    if summary is None:
        errors.append("F: TODO_V0.7.1.md: нет '**Сводно:** N спринт'")
    if progress is None:
        errors.append("F: TODO_V0.7.1.md: нет '**Прогресс: X/Y'")
    elif summary is not None:
        done, total = int(progress.group(1)), int(progress.group(2))
        if total != int(summary.group(1)):
            errors.append(
                f"F: TODO_V0.7.1.md: Сводно={summary.group(1)} спринтов,"
                f" Прогресс={done}/{total}"
            )
        if done > total:
            errors.append(f"F: TODO_V0.7.1.md: прогресс {done}/{total} > плана")
        elif (done, total) != EXPECTED_PROGRESS:
            errors.append(
                f"F: TODO_V0.7.1.md: прогресс {done}/{total},"
                f" ожидается {EXPECTED_PROGRESS[0]}/{EXPECTED_PROGRESS[1]}"
                " (S-87…S-89 впереди)"
            )
    return errors


# --- CLI


def _checkers(
    root: Path,
    tests_count: int | None,
    skip_tests: bool,
    collection_error: CollectError = "",
) -> list[tuple[str, str, Callable[[], list[str]]]]:
    """(id, заголовок, независимая проверка) — порядок A…F."""
    counts_title = "счётчики тестов"
    if skip_tests:
        counts_title += " (--skip-tests-count)"
    return [
        ("A", "версии согласованы", lambda: _check_versions(root)),
        ("B", "alembic head/миграции = README", lambda: _check_migrations(root)),
        (
            "C",
            counts_title,
            lambda: _check_counts(root, tests_count, skip_tests, collection_error),
        ),
        ("D", "один активный план", lambda: _check_active_plan(root)),
        ("E", "нет стрейл-маркеров", lambda: _check_stale(root)),
        ("F", "прогресс TODO_V0.7.1", lambda: _check_todo_progress(root)),
    ]


def lint(root: Path, tests_count: int | None, skip_tests: bool) -> list[str]:
    """Все проверки; список ошибок (пусто — документы совпадают с фактом)."""
    errors: list[str] = []
    for _check_id, _title, checker in _checkers(root, tests_count, skip_tests):
        errors.extend(checker())
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="doc-lint: проверка, что документация не разошлась с фактом.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="корень репозитория (default: каталог выше scripts/)",
    )
    parser.add_argument(
        "--tests-count",
        default="auto",
        metavar="auto|N",
        help="фактическое число backend-тестов для сверки с README (default: auto)",
    )
    parser.add_argument(
        "--skip-tests-count",
        action="store_true",
        help="не запускать pytest --collect-only (счётчик backend пропускается)",
    )
    return parser


def _resolve_tests_count(
    parser: argparse.ArgumentParser, raw: str
) -> int | str:
    if raw == "auto":
        return "auto"
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        parser.error("--tests-count: ожидается 'auto' или положительное целое")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    if not root.is_dir():
        print(f"doc-lint: корень не найден: {root}", file=sys.stderr)
        return 1

    tests_count: int | None = None
    collection_error: CollectError = ""
    resolved = _resolve_tests_count(parser, str(args.tests_count))
    if not args.skip_tests_count:
        if resolved == "auto":
            tests_count, collection_error = _collect_backend_tests(root / "backend")
            if tests_count is None:
                print(
                    f"doc-lint: pytest --collect-only: {collection_error}",
                    file=sys.stderr,
                )
        else:
            tests_count = int(resolved)

    checks = _checkers(root, tests_count, args.skip_tests_count, collection_error)
    failed = 0
    for check_id, title, checker in checks:
        try:
            errors = checker()
        except Exception as exc:  # noqa: BLE001 — упавшая проверка = FAIL, не краш
            errors = [f"{check_id}: проверка упала: {type(exc).__name__}: {exc}"]
        if errors:
            failed += 1
            for error in errors:
                print(f"[FAIL] {check_id} {title}: {error}")
        else:
            print(f"[ok] {check_id} {title}")
    print(f"doc-lint: {len(checks)} checks, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
