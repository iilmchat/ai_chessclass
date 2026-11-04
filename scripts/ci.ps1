# Локальный CI-прогон (RULES §6): полный контур в контейнерах compose.
# Причина: host-pip нестабильно таймаутит на PyPI; внутри docker-сети — ок.
# KI-001: работает только с проектом chessclass (имена контейнеров chessclass-*).

param(
    [switch]$SkipStack  # не применять миграции/seeds (только lint+typecheck+tests)
)

$ErrorActionPreference = "Stop"
$compose = "docker-compose.dev.yml"

Write-Host "[ci] config check..."
docker compose -f $compose config -q
if (-not $SkipStack) {
    Write-Host "[ci] alembic upgrade head..."
    docker compose -f $compose run --rm migrate
    if ($LASTEXITCODE -ne 0) { throw "migrate failed" }
    Write-Host "[ci] seeds..."
    docker compose -f $compose run --rm seed
    if ($LASTEXITCODE -ne 0) { throw "seed failed" }
    Write-Host "[ci] RAG eval gates (S-71, blocking)..."
    docker compose -f $compose run --rm api sh -c "python scripts/chess_rag_eval.py && python scripts/rag_gold_check.py"
    if ($LASTEXITCODE -ne 0) { throw "rag eval failed" }
}

Write-Host "[ci] ruff + mypy + pytest (in container)..."
docker compose -f $compose run --rm api sh -c "pip install -q -e '.[dev]' && ruff check . && mypy . && python -m pytest -q"
if ($LASTEXITCODE -ne 0) { throw "ci failed" }
Write-Host "[ci] OK"
