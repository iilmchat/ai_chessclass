# Локальный CI-прогон (RULES §6): полный контур в контейнерах compose.
# Причина: host-pip нестабильно таймаутит на PyPI; внутри docker-сети — ок.
# KI-001: работает только с проектом chessclass (имена контейнеров chessclass-*).

param(
    [switch]$SkipStack  # не применять миграции/seeds (только lint+typecheck+tests)
)

$ErrorActionPreference = "Stop"
$compose = "docker-compose.dev.yml"

# S-88: soft-check сертификатов. Warning (exit 1) не блокирует CI, critical
# (exit 2) — блокирует. Telegram из CI не отправляем: алертит ежедневный cron.
Write-Host "[ci] certificate expiry (soft-check)..."
& (Join-Path $PSScriptRoot "check-cert-expiry.ps1") -NoTelegram
if ($LASTEXITCODE -eq 2) { throw "certificate check: critical" }
if ($LASTEXITCODE -eq 1) {
    Write-Host "[ci] certificate warning — не блокирует" -ForegroundColor Yellow
}

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
# S-93: образ работает под appuser (uid 1000); editable-install в bind mount
# запрещён (egg-info root-owned), поэтому dev-инструменты ставим в user-site,
# а код импортируется из /srv/backend (cwd) без переустановки пакета.
docker compose -f $compose run --rm api sh -c "pip install -q --user 'pytest>=8.3' 'pytest-asyncio>=0.24' 'asgi-lifespan>=0.1' 'ruff>=0.8' 'mypy>=1.13' && ruff check --no-cache . && mypy --cache-dir=/tmp/mypy-cache . && python -m pytest -q -p no:cacheprovider"
if ($LASTEXITCODE -ne 0) { throw "ci failed" }
Write-Host "[ci] OK"
