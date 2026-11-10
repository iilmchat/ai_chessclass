# S-92: smoke multiprocess HTTP-метрик с двумя uvicorn-воркерами.
# Требует запущенные dev db/redis (после .\scripts\ci.ps1) и образ
# chessclass/backend:dev. Запуск: .\scripts\multiprocess-metrics-smoke.ps1
param(
    [int]$Port = 18022
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath ".").Path
$name = "chessclass-multiproc-selftest"
$base = "http://127.0.0.1:$Port"

docker rm -f $name 2>$null | Out-Null
try {
    docker run -d --rm --name $name --network chessclass-net `
        -p "127.0.0.1:${Port}:8020" `
        -v "${root}/backend:/srv/backend" -w /srv/backend `
        -e APP_ENV=dev `
        -e DATABASE_URL=postgresql+asyncpg://chess:chess_dev_2026@db:5432/chessclass `
        -e REDIS_URL=redis://redis:6379/0 `
        -e PROMETHEUS_MULTIPROC_DIR=/tmp/prom_multiproc `
        chessclass/backend:dev `
        uvicorn app.main:app --host 0.0.0.0 --port 8020 --workers 2 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "не удалось запустить 2 uvicorn-воркера" }

    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        $code = & curl.exe -s -o NUL -w "%{http_code}" "$base/healthz"
        if ($code -eq "200") { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        docker logs --tail=100 $name
        throw "API (2 workers) не готов за 60 с"
    }

    foreach ($i in 1..30) {
        & curl.exe -s -o NUL "$base/healthz" | Out-Null
    }
    $metrics = (& curl.exe -s "$base/metrics") -join "`n"
    $matches = [regex]::Matches(
        $metrics,
        'chessclass_http_requests_total\{[^}]*route="/healthz"[^}]*\}\s+(\d+)'
    )
    $total = ($matches | ForEach-Object { [int]$_.Groups[1].Value } | Measure-Object -Sum).Sum
    if (-not $total -or $total -lt 30) {
        throw "ожидалось >=30 healthz-запросов в /metrics, получено $total"
    }
    Write-Host "[multiproc] 2 workers, healthz requests in aggregated /metrics: $total"
} finally {
    docker rm -f $name 2>$null | Out-Null
}
