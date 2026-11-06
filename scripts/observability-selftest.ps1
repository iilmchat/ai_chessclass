# S-82: self-test prod-observability (OTel Collector + Tempo + Prometheus +
# Alertmanager → Telegram + Grafana).
#
# Static-проверки всегда: compose-конфиг, правила promtool, рендер конфигов
# Alertmanager/Prometheus и их валидация (amtool/promtool).
# Runtime (-Stack): поднимает профиль observability, проверяет готовность,
# targets, маршруты Alertmanager, mTLS-приём трейса в Tempo и Grafana,
# затем останавливает ТОЛЬКО контейнеры профиля (stop, volumes сохраняются).
#
# Секреты не печатаются: для рендера используются фиктивные значения.
#
# Запуск:
#   .\scripts\observability-selftest.ps1              # только конфиги
#   .\scripts\observability-selftest.ps1 -Stack       # + runtime smoke
param(
    [switch]$Stack,
    [string]$EnvFile = ".env.prod.example",
    [string]$Compose = "docker-compose.prod.yml"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath ".").Path
$prod = Join-Path $root "deploy/observability/prod"
$alerts = Join-Path $root "deploy/observability/alerts.yml"
$tmp = Join-Path $root ".verify/obs-selftest"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

$script:failed = 0
function Check {
    param([string]$Name, [scriptblock]$Body)
    try {
        & $Body | Out-Null
        Write-Host "[ok] $Name" -ForegroundColor Green
    } catch {
        $script:failed++
        Write-Host "[FAIL] ${Name}: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

# --- 1. Compose: профиль observability валиден ------------------------------
Check "compose config (-q, prod + observability)" {
    docker compose --env-file $EnvFile -f $Compose config -q
    Assert-True ($LASTEXITCODE -eq 0) "docker compose config -q exit=$LASTEXITCODE"
}
Check "observability не входит в дефолтный набор сервисов" {
    $default = (docker compose --env-file $EnvFile -f $Compose config --services) -join ","
    foreach ($service in @("tempo", "otel-collector", "prometheus", "alertmanager", "grafana")) {
        Assert-True ($default -notmatch "(^|,)$service(,|$)") "профиль не изолирован: $service"
    }
}
Check "профиль observability включает 5 сервисов" {
    $withProfile = (
        docker compose --env-file $EnvFile -f $Compose --profile observability config --services
    ) -join ","
    foreach ($service in @("tempo", "otel-collector", "prometheus", "alertmanager", "grafana")) {
        Assert-True ($withProfile -match "(^|,)$service(,|$)") "нет сервиса $service"
    }
}

# --- 2. Правила Prometheus ---------------------------------------------------
Check "promtool check rules (alerts.yml)" {
    $out = docker run --rm --entrypoint promtool `
        -v "${alerts}:/tmp/alerts.yml:ro" prom/prometheus:v3.1.0 `
        check rules /tmp/alerts.yml 2>&1
    Assert-True (($out -join "`n") -match "SUCCESS: \d+ rules found") ($out -join " ")
}

# --- 3. Рендер и валидация Alertmanager (фиктивные секреты) ------------------
Check "amtool check-config (рендер alertmanager.yml.tmpl)" {
    $rendered = Join-Path $tmp "alertmanager.rendered.yml"
    $token = "selftest-dummy-token-not-a-real-secret"
    (Get-Content -Raw (Join-Path $prod "alertmanager.yml.tmpl")).
        Replace("__TELEGRAM_BOT_TOKEN__", $token).
        Replace("__TELEGRAM_ALERT_CHAT_ID__", "-1001234567890") |
        Set-Content -LiteralPath $rendered -NoNewline -Encoding utf8
    $out = docker run --rm `
        -v "${rendered}:/tmp/a.yml:ro" `
        -v "${prod}/telegram.tmpl:/etc/alertmanager/telegram.tmpl:ro" `
        --entrypoint /bin/amtool prom/alertmanager:v0.28.1 check-config /tmp/a.yml 2>&1
    Assert-True (($out -join "`n") -match "SUCCESS") ($out -join " ")
    Remove-Item -LiteralPath $rendered -Force
}

# --- 4. Рендер и валидация Prometheus (фиктивный токен) ---------------------
Check "promtool check config (рендер prometheus.yml.tmpl)" {
    $rendered = Join-Path $tmp "prometheus.rendered.yml"
    (Get-Content -Raw (Join-Path $prod "prometheus.yml.tmpl")).
        Replace("__METRICS_TOKEN__", "selftest-token") |
        Set-Content -LiteralPath $rendered -NoNewline -Encoding utf8
    $out = docker run --rm --entrypoint promtool `
        -v "${rendered}:/tmp/p.yml:ro" `
        -v "${alerts}:/etc/prometheus-rules/alerts.yml:ro" `
        prom/prometheus:v3.1.0 check config /tmp/p.yml 2>&1
    Assert-True (($out -join "`n") -match "SUCCESS") ($out -join " ")
    Remove-Item -LiteralPath $rendered -Force
}

if (-not $Stack) {
    if ($script:failed -gt 0) { exit 1 }
    Write-Host "[obs-selftest] static checks OK (runtime: добавьте -Stack)" -ForegroundColor Green
    exit 0
}

# --- 5. Runtime smoke профиля ------------------------------------------------
$env:TELEGRAM_BOT_TOKEN = "selftest-dummy-token-not-a-real-secret"
$env:TELEGRAM_ALERT_CHAT_ID = if ($env:TELEGRAM_ALERT_CHAT_ID) { $env:TELEGRAM_ALERT_CHAT_ID } else { "-1001234567890" }
$prom = "http://127.0.0.1:$(if ($env:PROMETHEUS_PORT) { $env:PROMETHEUS_PORT } else { '9092' })"
$am = "http://127.0.0.1:$(if ($env:ALERTMANAGER_PORT) { $env:ALERTMANAGER_PORT } else { '9093' })"
$grafanaPort = if ($env:GRAFANA_PORT) { $env:GRAFANA_PORT } else { "3002" }

try {
    Check "профиль observability поднимается" {
        docker compose --env-file $EnvFile -f $Compose --profile observability `
            up -d tempo otel-collector prometheus alertmanager grafana 2>&1 | Out-Null
        $deadline = (Get-Date).AddSeconds(180)
        while ((Get-Date) -lt $deadline) {
            $ready = $true
            foreach ($url in @("$prom/-/ready", "$am/-/ready")) {
                try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 | Out-Null }
                catch { $ready = $false }
            }
            if ($ready) { return }
            Start-Sleep -Seconds 3
        }
        throw "Prometheus/Alertmanager не готовы за 180 с"
    }
    Check "Prometheus видит все targets" {
        $targets = (Invoke-RestMethod -Uri "$prom/api/v1/targets").data.activeTargets
        $jobs = $targets | ForEach-Object { $_.labels.job }
        foreach ($job in @("chessclass-api", "otel-collector", "prometheus", "alertmanager")) {
            Assert-True ($jobs -contains $job) "target не найден: $job"
        }
        $down = $targets | Where-Object { $_.health -ne "up" }
        Assert-True ($down.Count -eq 0) ("targets down: " + (($down | ForEach-Object { $_.labels.job }) -join ","))
    }
    Check "правила загружены в Prometheus (5)" {
        $groups = (Invoke-RestMethod -Uri "$prom/api/v1/rules").data.groups
        $count = ($groups | ForEach-Object { $_.rules.Count } | Measure-Object -Sum).Sum
        Assert-True ($count -eq 5) "rules=$count"
    }
    Check "Alertmanager связан с Prometheus" {
        $ams = (Invoke-RestMethod -Uri "$prom/api/v1/alertmanagers").data.activeAlertmanagers
        Assert-True ($ams.Count -ge 1) "нет активных Alertmanager"
    }
    Check "маршруты Alertmanager: critical→telegram-critical, warning→telegram" {
        $container = "chessclass-prod-alertmanager"
        $critical = docker exec $container amtool config routes test `
            --config.file=/tmp/alertmanager.yml severity=critical alertname=ChessClassHighErrorRate component=api 2>&1
        $warning = docker exec $container amtool config routes test `
            --config.file=/tmp/alertmanager.yml severity=warning alertname=ChessClassDLQGrowth component=worker 2>&1
        Assert-True (($critical -join "`n") -match "telegram-critical") "critical: $critical"
        Assert-True (($warning -join "`n") -match "telegram") "warning: $warning"
    }
    Check "mTLS: трейс принимается Tempo и читается обратно" {
        $traceId = -join ((1..32) | ForEach-Object { "{0:x}" -f (Get-Random -Max 16) })
        $spanId = -join ((1..16) | ForEach-Object { "{0:x}" -f (Get-Random -Max 16) })
        $start = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() * 1000000
        $payload = @{
            resourceSpans = @(@{
                resource = @{ attributes = @(@{ key = "service.name"; value = @{ stringValue = "chessclass-api" } }) }
                scopeSpans = @(@{ spans = @(@{
                    traceId = $traceId; spanId = $spanId; name = "s82.selftest"; kind = 1
                    startTimeUnixNano = "$start"; endTimeUnixNano = "$($start + 5000000)"
                }) })
            })
        } | ConvertTo-Json -Depth 12 -Compress
        $payloadFile = Join-Path $tmp "otlp.json"
        Set-Content -LiteralPath $payloadFile -Value $payload -NoNewline -Encoding ascii
        $certs = Join-Path $root "deploy/internal-certs"
        $post = docker run --rm --network chessclass-prod-net `
            -v "${certs}:/certs:ro" -v "${payloadFile}:/payload.json:ro" alpine/curl `
            -sS --cacert /certs/ca.crt --cert /certs/collector.crt --key /certs/collector.key `
            -X POST "https://tempo:4318/v1/traces" -H "Content-Type: application/json" `
            --data-binary "@/payload.json" -w "HTTP:%{http_code}" 2>&1
        Assert-True (($post -join "`n") -match "HTTP:200") ("ingest: " + ($post -join " "))
        $read = docker run --rm --network chessclass-prod-net alpine/curl `
            -sS -o /dev/null -w "HTTP:%{http_code}" "http://tempo:3200/api/traces/$traceId" 2>&1
        Assert-True (($read -join "`n") -match "HTTP:200") ("read: " + ($read -join " "))
        Remove-Item -LiteralPath $payloadFile -Force
    }
    Check "Grafana: health + datasources Prometheus/Tempo" {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$grafanaPort/api/health"
        Assert-True ($health.database -eq "ok") "grafana database=$($health.database)"
        $password = $env:GRAFANA_ADMIN_PASSWORD
        if (-not $password) { $password = "CHANGE_ME_GRAFANA_PASSWORD" }
        $user = if ($env:GRAFANA_ADMIN_USER) { $env:GRAFANA_ADMIN_USER } else { "chessadmin" }
        $pair = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${user}:${password}"))
        $datasources = Invoke-RestMethod -Uri "http://127.0.0.1:$grafanaPort/api/datasources" `
            -Headers @{ Authorization = "Basic $pair" }
        $types = $datasources | ForEach-Object { $_.type }
        Assert-True ($types -contains "prometheus") "нет datasource prometheus"
        Assert-True ($types -contains "tempo") "нет datasource tempo"
    }
} finally {
    # Останавливаем только профиль: базовый стек не трогаем, volumes сохраняем.
    docker compose --env-file $EnvFile -f $Compose --profile observability `
        stop tempo otel-collector prometheus alertmanager grafana 2>&1 | Out-Null
}

if ($script:failed -gt 0) {
    Write-Host "[obs-selftest] FAILED: $($script:failed)" -ForegroundColor Red
    exit 1
}
Write-Host "[obs-selftest] OK" -ForegroundColor Green
