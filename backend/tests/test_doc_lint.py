"""S-60: чистые хелперы scripts/doc_lint.py (без БД, сети и subprocess)."""

import importlib.util
import os
from pathlib import Path

_HERE = Path(__file__).resolve()


def _find_script() -> Path:
    """Найти scripts/doc_lint.py: host/CI checkout, /repo-mount или env override."""
    candidates: list[Path] = []
    override = os.environ.get("DOC_LINT_SCRIPT")
    if override:
        candidates.append(Path(override))
    # host/CI checkout: backend/tests/... -> корень репозитория
    candidates.append(_HERE.parents[2] / "scripts" / "doc_lint.py")
    # локальная проверка в контейнере: репозиторий смонтирован в /repo
    candidates.append(Path("/repo/scripts/doc_lint.py"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "scripts/doc_lint.py не найден; смонтируйте репозиторий в /repo "
        "или задайте DOC_LINT_SCRIPT"
    )


def _load_doc_lint():
    spec = importlib.util.spec_from_file_location("doc_lint_script", _find_script())
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


doc_lint = _load_doc_lint()
REPO = _find_script().parents[1]


def test_alembic_graph_matches_repo() -> None:
    head, count = doc_lint._alembic_graph(REPO)

    assert head == "0032_s73_async_tracing"
    assert count == 32


def test_collect_versions_consistent() -> None:
    versions = doc_lint._collect_versions(REPO)

    assert versions
    assert all(value == "0.4.0" for value in versions.values())


def test_stale_markers_detected(tmp_path: Path) -> None:
    dirty = "# Документ\n16/16 спринтов\n174 passed\nv0.2.0 Draft\n"
    hits = doc_lint._stale_hits(dirty)

    assert len(hits) == 3
    assert any("16/16" in hit for hit in hits)
    assert any("174 passed" in hit for hit in hits)
    assert any("v0.2.0 Draft" in hit for hit in hits)

    clean = "# Документ\n" + "Активный этап v0.4.0, прогресс 1/12.\n"
    assert doc_lint._stale_hits(clean) == []

    (tmp_path / "dirty.md").write_text(dirty, encoding="utf-8")
    assert doc_lint._check_no_stale(tmp_path, ["dirty.md"])

    (tmp_path / "clean.md").write_text(clean, encoding="utf-8")
    assert doc_lint._check_no_stale(tmp_path, ["clean.md"]) == []
    # Отсутствующий активный документ — тоже ошибка E.
    assert doc_lint._check_no_stale(tmp_path, ["missing.md"])
