# ChessClass — отдельный e2e-стенд (S-36).
# Примеры:
#   .\scripts\e2e.ps1 up      # поднять 8021/3201, миграции+seeds
#   .\scripts\e2e.ps1 test    # reset -> up -> Playwright -> cleanup
#   .\scripts\e2e.ps1 reset   # удалить e2e-volumes
#   .\scripts\e2e.ps1 down    # остановить, volumes сохранить
#   .\scripts\e2e.ps1 logs

param(
    [ValidateSet("up", "down", "reset", "test", "logs")]
    [string]$Action = "test"
)

$ErrorActionPreference = "Stop"
$compose = "docker-compose.e2e.yml"

$env:E2E_API_ORIGIN = "http://127.0.0.1:8021"
$env:E2E_BASE_URL = "http://127.0.0.1:3201"
$env:API_PROXY = "http://127.0.0.1:8021"
$env:E2E_DATABASE_URL = "postgresql://chess:chess_e2e@127.0.0.1:5439/chessclass"

function Wait-E2EStack {
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $ready = Invoke-RestMethod -Uri "http://127.0.0.1:8021/readyz" -TimeoutSec 3
            if ($ready.status -eq "ready") {
                $web = Invoke-WebRequest -Uri "http://127.0.0.1:3201/" -UseBasicParsing -TimeoutSec 3
                if ($web.StatusCode -eq 200) {
                    Write-Host "[e2e] stack ready (8021/3201)" -ForegroundColor Green
                    return
                }
            }
        } catch {
            # Стек ещё стартует.
        }
        Start-Sleep -Seconds 2
    }
    docker compose -f $compose logs --tail=80 api setup web
    throw "e2e stack не поднялся за 120 с"
}

switch ($Action) {
    "up" {
        docker compose -f $compose up -d --build
        Wait-E2EStack
    }
    "down" {
        docker compose -f $compose down --remove-orphans
    }
    "reset" {
        docker compose -f $compose down -v --remove-orphans
    }
    "logs" {
        docker compose -f $compose logs --tail=120
    }
    "test" {
        $code = 0
        # Чистая БД/Redis на каждый прогон.
        docker compose -f $compose down -v --remove-orphans
        try {
            docker compose -f $compose up -d --build
            Wait-E2EStack
            Push-Location frontend
            try {
                npm run test:e2e
                $code = $LASTEXITCODE
            } finally {
                Pop-Location
            }
        } finally {
            docker compose -f $compose down -v --remove-orphans
        }
        exit $code
    }
}
