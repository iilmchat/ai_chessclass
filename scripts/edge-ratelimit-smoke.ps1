# S-90: smoke edge rate-limit (nginx). Проверяет, что 10 запросов к
# /api/v1/auth/* проходят, а 11-й получает 429 (не 503), и что edge.conf
# содержит нужные зоны/заголовки.
#
# Запуск: .\scripts\edge-ratelimit-smoke.ps1
param(
    [int]$Port = 18080,
    [string]$Image = "nginx:1.27-alpine"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath ".").Path
$edge = Get-Content -Raw -LiteralPath (Join-Path $root "deploy/nginx/edge.conf")

foreach ($needle in @(
    "limit_req_zone `$binary_remote_addr zone=auth_rl:10m rate=10r/m;",
    "limit_req_zone `$binary_remote_addr zone=api_rl:10m rate=60r/m;",
    "location /api/v1/auth/",
    "limit_req zone=auth_rl burst=9 nodelay;",
    "limit_req zone=api_rl burst=30 nodelay;",
    "limit_req_status 429;",
    "X-Forwarded-For `$proxy_add_x_forwarded_for",
    "X-Real-IP `$remote_addr"
)) {
    if (-not $edge.Contains($needle)) {
        throw "edge.conf: не найдено '$needle'"
    }
}

$tmp = Join-Path $root ".verify/edge-ratelimit"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$config = Join-Path $tmp "nginx.conf"
@'
events {}
http {
  limit_req_zone $binary_remote_addr zone=auth_rl:10m rate=10r/m;
  server {
    listen 8081;
    location / { return 200 "ok"; }
  }
  server {
    listen 8080;
    location = /__ready { return 204; }
    location /api/v1/auth/ {
      limit_req zone=auth_rl burst=9 nodelay;
      limit_req_status 429;
      proxy_pass http://127.0.0.1:8081;
    }
  }
}
'@ | Set-Content -LiteralPath $config -Encoding ascii

$name = "chessclass-edge-rl-selftest"
$base = "http://127.0.0.1:$Port"
docker rm -f $name 2>$null | Out-Null
try {
    docker run -d --rm --name $name -p "127.0.0.1:${Port}:8080" `
        -v "${config}:/etc/nginx/nginx.conf:ro" $Image | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "не удалось запустить nginx ($Image)"
    }

    $ready = $false
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $code = & curl.exe -s -o NUL -w "%{http_code}" "$base/__ready"
        if ($code -eq "204") { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "nginx не готов за 30 с" }

    $codes = @()
    foreach ($i in 1..11) {
        $codes += [int](& curl.exe -s -o NUL -w "%{http_code}" "$base/api/v1/auth/login")
    }
    $firstTen = $codes[0..9]
    if (($firstTen | Where-Object { $_ -ne 200 }).Count -gt 0) {
        throw "ожидались 200 для первых 10 запросов: $($codes -join ',')"
    }
    if ($codes[10] -ne 429) {
        throw "11-й запрос должен быть 429, получено $($codes[10])"
    }
    if ($codes -contains 503) {
        throw "nginx вернул 503 вместо 429"
    }
    Write-Host "[edge-ratelimit] auth: 10x200, 11th=429; edge.conf static OK"
} finally {
    docker rm -f $name 2>$null | Out-Null
}
