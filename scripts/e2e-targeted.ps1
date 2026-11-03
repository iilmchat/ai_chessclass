# Целевой e2e-прогон по списку спецификаций (для отладки S-65):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/e2e-targeted.ps1 e2e/full-journey.spec.ts e2e/pvp.spec.ts
# Стек пересоздаётся (reset + up), тома НЕ удаляются после теста — для отладки.
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$SpecArgs)

$ErrorActionPreference = "Stop"
$compose = "docker-compose.e2e.yml"
$env:E2E_API_ORIGIN = "http://127.0.0.1:8021"
$env:E2E_BASE_URL = "http://127.0.0.1:3201"
$env:API_PROXY = "http://127.0.0.1:8021"
$env:E2E_DATABASE_URL = "postgresql://chess:chess_e2e@127.0.0.1:5439/chessclass"

docker compose -f $compose down -v --remove-orphans | Out-Null
docker compose -f $compose up -d --build | Out-Null

for ($i = 0; $i -lt 60; $i++) {
    try {
        $ready = Invoke-RestMethod -Uri "http://127.0.0.1:8021/readyz" -TimeoutSec 3
        if ($ready.status -eq "ready") {
            Write-Host "[e2e] stack ready" -ForegroundColor Green
            break
        }
    } catch {
        # стек ещё стартует
    }
    Start-Sleep -Seconds 2
}
if (-not $ready -or $ready.status -ne "ready") {
    docker compose -f $compose logs --tail=60 api setup
    throw "e2e stack не поднялся"
}

Push-Location frontend
try {
    npx playwright test @SpecArgs --reporter=list
} finally {
    Pop-Location
}
