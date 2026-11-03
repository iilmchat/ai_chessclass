"""S-62: hash-lock — release-truth проверки воспроизводимой сборки.

Все проверяемые файлы (requirements.lock, Dockerfile) лежат в backend/ —
как и тесты, они в bind-mount контейнера локально и в CI-checkout.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _lock_blocks() -> list[list[str]]:
    lock = BACKEND / "requirements.lock"
    assert lock.is_file(), (
        "backend/requirements.lock отсутствует: перегенерируйте "
        "pip-compile --generate-hashes (RULES §6)"
    )
    lines = lock.read_text(encoding="utf-8").splitlines()
    blocks: list[list[str]] = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "-", "\t")):
            if blocks:
                blocks[-1].append(line)
            continue
        blocks.append([line])
    return blocks


def test_lock_every_entry_has_hashes():
    """Каждая запись в lock снабжена `--hash=sha256` (multi-line блоки)."""
    blocks = [b for b in _lock_blocks() if not b[0].startswith("-r")]
    assert blocks, "requirements.lock пуст"
    bad = [b[0].split("==")[0] for b in blocks if "--hash=sha256:" not in "\n".join(b)]
    assert not bad, f"записи без hash: {bad}"


def test_dockerfile_builds_only_from_lock():
    """Сборка: установка из lock c --require-hashes; сам проект — --no-deps."""
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert "--require-hashes -r requirements.lock" in dockerfile
    assert "--no-deps -e ." in dockerfile, (
        "self-install должен быть --no-deps (иначе pip снова уйдёт в PyPI)"
    )
    assert "pip install" in dockerfile and "-r requirements.lock" in dockerfile


def test_stockfish_sha256_pinned_and_checked():
    """SHA256 архива Stockfish зафиксирован; mismatch ломает build."""
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(r"STOCKFISH_SHA256=([0-9a-f]{64})", dockerfile)
    assert match, "в Dockerfile нет STOCKFISH_SHA256=<64 hex>"
    assert "hash mismatch" in dockerfile, (
        "Dockerfile: нет проверки hash архива Stockfish перед установкой"
    )
