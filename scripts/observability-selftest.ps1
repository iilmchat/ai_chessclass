# S-82/S-87/S-88: self-test prod-observability (OTel Collector + Tempo +
# Prometheus + Alertmanager → Telegram/email + node-exporter + Grafana).
#
# Static-проверки всегда: compose-конфиг, правила promtool, рендер конфигов
# Alertmanager/Prometheus (entrypoint-скриптами) и их валидация
# (amtool/promtool), маскировка секретов в логах, пороги
# scripts/check-cert-expiry.ps1 (ok/warning/critical).
# Runtime (-Stack): поднимает профиль observability, проверяет готовность,
# targets, маршруты Alertmanager, второй receiver (email) через локальный
# SMTP-приёмник, маскировку bot token в логах, mTLS-приём трейса в Tempo,
# gauges S-88 в /metrics и Grafana, затем останавливает ТОЛЬКО контейнеры
# профиля (stop, volumes сохраняются).
#
# Секреты не печатаются: для рендера используются фиктивные значения, токен
# для проверки маскировки собирается из частей (gitleaks не ловит fixture).
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

function Render-Alertmanager {
    param([string]$Name, [hashtable]$Env)
    $dir = Join-Path $tmp "render-$Name"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $dockerArgs = @("run", "--rm")
    foreach ($key in $Env.Keys) { $dockerArgs += @("-e", "$key=$($Env[$key])") }
    $dockerArgs += @(
        "-v", "${prod}:/etc/alertmanager:ro",
        "-v", "${dir}:/out",
        "--entrypoint", "/bin/sh",
        "prom/alertmanager:v0.28.1",
        "-c", "/etc/alertmanager/alertmanager-render.sh /out/am.yml"
    )
    & docker @dockerArgs 2>&1 | Out-Null
    Assert-True ($LASTEXITCODE -eq 0) "render '$Name' exit=$LASTEXITCODE"
    $file = Join-Path $dir "am.yml"
    Assert-True (Test-Path -LiteralPath $file) "render '$Name': нет $file"
    return $file
}

function Assert-AmtoolConfig {
    param([string]$File)
    $out = docker run --rm `
        -v "${File}:/tmp/a.yml:ro" `
        -v "${prod}/telegram.tmpl:/etc/alertmanager/telegram.tmpl:ro" `
        --entrypoint /bin/amtool prom/alertmanager:v0.28.1 check-config /tmp/a.yml 2>&1
    Assert-True (($out -join "`n") -match "SUCCESS") ($out -join " ")
}

function Get-AmtoolRoute {
    param([string]$File, [string[]]$Selector)
    $out = docker run --rm `
        -v "${File}:/tmp/a.yml:ro" `
        --entrypoint /bin/amtool prom/alertmanager:v0.28.1 `
        config routes test --config.file=/tmp/a.yml $Selector 2>&1
    return ($out -join "`n")
}

# --- 1. Compose: профиль observability валиден ------------------------------
$obsServices = @("tempo", "otel-collector", "node-exporter", "prometheus", "alertmanager", "grafana")

Check "compose config (-q, prod + observability)" {
    docker compose --env-file $EnvFile -f $Compose config -q
    Assert-True ($LASTEXITCODE -eq 0) "docker compose config -q exit=$LASTEXITCODE"
}
Check "observability не входит в дефолтный набор сервисов" {
    $default = (docker compose --env-file $EnvFile -f $Compose config --services) -join ","
    foreach ($service in $obsServices) {
        Assert-True ($default -notmatch "(^|,)$service(,|$)") "профиль не изолирован: $service"
    }
}
Check "профиль observability включает 6 сервисов" {
    $withProfile = (
        docker compose --env-file $EnvFile -f $Compose --profile observability config --services
    ) -join ","
    foreach ($service in $obsServices) {
        Assert-True ($withProfile -match "(^|,)$service(,|$)") "нет сервиса $service"
    }
}

# --- 2. Правила Prometheus ---------------------------------------------------
Check "promtool check rules (alerts.yml)" {
    $out = docker run --rm --entrypoint promtool `
        -v "${alerts}:/tmp/alerts.yml:ro" prom/prometheus:v3.1.0 `
        check rules /tmp/alerts.yml 2>&1
    Assert-True (($out -join "`n") -match "SUCCESS: 12 rules found") ($out -join " ")
    $content = Get-Content -Raw -LiteralPath $alerts
    foreach ($name in @(
        "ChessClassObservabilityDiskFull",
        "ChessClassEmailOutboxStuck",
        "ChessClassRetentionArchiveStale",
        "ChessClassLegalHoldActive",
        "ChessClassRetentionFailed",
        "ChessClassBackupFailed",
        "ChessClassBackupRestoreFailed"
    )) {
        Assert-True ($content -match $name) "нет правила $name"
    }
}

# --- 3. Рендер Alertmanager: email выключен (обратная совместимость) ----------
Check "render alertmanager без email + amtool check-config" {
    $file = Render-Alertmanager -Name "no-email" -Env @{
        TELEGRAM_BOT_TOKEN = "selftest-dummy-token-not-a-real-secret"
        TELEGRAM_ALERT_CHAT_ID = "-1001234567890"
        SMTP_HOST = ""
        ALERT_EMAIL_TO = ""
    }
    Assert-AmtoolConfig -File $file
    $content = Get-Content -Raw -LiteralPath $file
    Assert-True ($content -notmatch "(?m)^\s*-\s+name:\s+email\s*$") "email receiver не удалён"
    $route = Get-AmtoolRoute -File $file `
        -Selector @("severity=critical", "alertname=X", "component=observability")
    Assert-True ($route -match "telegram-critical") "critical: $route"
    Assert-True ($route -notmatch "email") "critical попал в email без SMTP: $route"
}

# --- 4. Рендер Alertmanager: email включён (второй receiver) -----------------
Check "render alertmanager с email + amtool check-config" {
    $file = Render-Alertmanager -Name "email" -Env @{
        TELEGRAM_BOT_TOKEN = "selftest-dummy-token-not-a-real-secret"
        TELEGRAM_ALERT_CHAT_ID = "-1001234567890"
        SMTP_HOST = "smtp.selftest.invalid"
        SMTP_PORT = "1025"
        SMTP_FROM = "alerts@selftest.invalid"
        SMTP_USER = "selftest"
        SMTP_PASSWORD = "selftest-password"
        SMTP_STARTTLS = "false"
        ALERT_EMAIL_TO = "duty@selftest.invalid"
    }
    Assert-AmtoolConfig -File $file
    $content = Get-Content -Raw -LiteralPath $file
    Assert-True ($content -match "(?m)^\s*-\s+name:\s+email\s*$") "нет email receiver"
    Assert-True ($content -match 'smarthost: "smtp.selftest.invalid:1025"') "нет smarthost"
    Assert-True ($content -match "require_tls: false") "require_tls не false"
    $critical = Get-AmtoolRoute -File $file `
        -Selector @("severity=critical", "alertname=X", "component=observability")
    $warning = Get-AmtoolRoute -File $file `
        -Selector @("severity=warning", "alertname=Y", "component=worker")
    Assert-True ($critical -match "telegram-critical" -and $critical -match "email") "critical: $critical"
    Assert-True ($warning -match "telegram" -and $warning -match "email") "warning: $warning"
}

# --- 5. Маскировка секретов в логах Alertmanager -----------------------------
Check "redact-logs.awk маскирует bot token и Bearer" {
    $fakeToken = "424242" + ":" + "selftest" + "-dummy"
    $payload = @"
https://api.telegram.org/bot$fakeToken/sendMessage
Authorization: Bearer selftest-bearer-value
"@
    $redacted = (
        $payload | docker run --rm -i `
            -v "${prod}:/etc/alertmanager:ro" `
            --entrypoint /bin/awk prom/alertmanager:v0.28.1 `
            -f /etc/alertmanager/redact-logs.awk 2>&1
    ) -join "`n"
    Assert-True ($redacted -match "bot<REDACTED>") "нет bot<REDACTED>: $redacted"
    Assert-True (-not ($redacted -match [regex]::Escape($fakeToken))) "raw token в выводе"
    Assert-True ($redacted -match "Authorization: Bearer <REDACTED>") "нет Bearer<REDACTED>: $redacted"
}
Check "в prod-конфигах observability нет токен-подобных строк" {
    $hits = @(
        Get-ChildItem -LiteralPath $prod -File -Recurse |
            Select-String -Pattern 'bot\d+:[A-Za-z0-9_-]{20,}'
    )
    Assert-True ($hits.Count -eq 0) "найдено: $(($hits | ForEach-Object { $_.Path }) -join ',')"
}

# --- 5b. Проверка срока сертификатов (S-88) ---------------------------------
Check "check-cert-expiry: ok/warning/critical exit codes" {
    $certDir = Join-Path $tmp "cert-expiry"
    New-Item -ItemType Directory -Force -Path $certDir | Out-Null
    $generated = docker run --rm -v "${certDir}:/certs" --entrypoint sh alpine/openssl `
        -c 'for d in 100 10 2; do openssl req -x509 -nodes -newkey rsa:2048 -days "$d" -keyout "/certs/key-$d.pem" -out "/certs/cert-$d.crt" -subj "/CN=selftest-$d" >/dev/null 2>&1 || exit 1; done' 2>&1
    Assert-True ($LASTEXITCODE -eq 0) "генерация: $($generated -join ' ')"
    $script = Join-Path $root "scripts/check-cert-expiry.ps1"
    & $script -Paths @((Join-Path $certDir "cert-100.crt")) -NoTelegram | Out-Null
    Assert-True ($LASTEXITCODE -eq 0) "ok: exit=$LASTEXITCODE"
    & $script -Paths @((Join-Path $certDir "cert-10.crt")) -NoTelegram | Out-Null
    Assert-True ($LASTEXITCODE -eq 1) "warning: exit=$LASTEXITCODE"
    & $script -Paths @((Join-Path $certDir "cert-2.crt")) -NoTelegram | Out-Null
    Assert-True ($LASTEXITCODE -eq 2) "critical: exit=$LASTEXITCODE"
}

# --- 6. Рендер и валидация Prometheus (фиктивный токен) ---------------------
Check "promtool check config (рендер prometheus.yml.tmpl)" {
    $rendered = Join-Path $tmp "prometheus.rendered.yml"
    (Get-Content -Raw (Join-Path $prod "prometheus.yml.tmpl")).
        Replace("__METRICS_TOKEN__", "selftest-token") |
        Set-Content -LiteralPath $rendered -NoNewline -Encoding utf8
    $content = Get-Content -Raw -LiteralPath $rendered
    Assert-True ($content -match "job_name: node-exporter") "нет scrape node-exporter"
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

# --- 7. Runtime smoke профиля ------------------------------------------------
$fakeToken = "424242" + ":" + "selftest" + "-dummy"
$sinkName = "chessclass-selftest-smtp"
$env:TELEGRAM_BOT_TOKEN = $fakeToken
$env:TELEGRAM_ALERT_CHAT_ID = if ($env:TELEGRAM_ALERT_CHAT_ID) { $env:TELEGRAM_ALERT_CHAT_ID } else { "-1001234567890" }
# Детерминированный сбой Telegram без egress — проверяем маскировку в логе.
$env:ALERT_TELEGRAM_API_URL = "http://127.0.0.1:9"
# Второй receiver: локальный SMTP-приёмник, TLS/auth выключены (только selftest).
$env:SMTP_HOST = $sinkName
$env:SMTP_PORT = "1025"
$env:SMTP_FROM = "alerts@selftest.invalid"
$env:SMTP_USER = ""
$env:SMTP_PASSWORD = ""
$env:SMTP_STARTTLS = "false"
$env:ALERT_EMAIL_TO = "duty@selftest.invalid"

$prom = "http://127.0.0.1:$(if ($env:PROMETHEUS_PORT) { $env:PROMETHEUS_PORT } else { '9092' })"
$am = "http://127.0.0.1:$(if ($env:ALERTMANAGER_PORT) { $env:ALERTMANAGER_PORT } else { '9093' })"
$grafanaPort = if ($env:GRAFANA_PORT) { $env:GRAFANA_PORT } else { "3002" }

try {
    Check "профиль observability поднимается" {
        docker compose --env-file $EnvFile -f $Compose --profile observability `
            up -d tempo otel-collector node-exporter prometheus alertmanager grafana 2>&1 | Out-Null
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
    Check "SMTP-приёмник для второго receiver запущен" {
        docker rm -f $sinkName 2>&1 | Out-Null
        docker run -d --name $sinkName --network chessclass-prod-net `
            -v "${root}/scripts/observability-smtp-sink.py:/sink.py:ro" `
            python:3.12-slim python /sink.py 2>&1 | Out-Null
        $deadline = (Get-Date).AddSeconds(30)
        do {
            $logs = (docker logs $sinkName 2>&1) -join "`n"
            if ($logs -match "SMTP sink ready") { return }
            Start-Sleep -Seconds 1
        } while ((Get-Date) -lt $deadline)
        throw "SMTP-приёмник не готов"
    }
    Check "Prometheus видит все targets" {
        # Первый scrape идёт через scrape_interval (15 с): readiness Prometheus
        # не означает, что target уже опрошен. Ждём до 90 с.
        # Профиль observability можно проверять без базового стека: target
        # chessclass-api должен быть в конфиге, но его down допустим, если api
        # не запущен (это ответственность отдельного smoke базового стека).
        $required = @("otel-collector", "node-exporter", "prometheus", "alertmanager")
        $expected = @("chessclass-api") + $required
        $deadline = (Get-Date).AddSeconds(90)
        $targets = @()
        $jobs = @()
        $down = @()
        do {
            $targets = (Invoke-RestMethod -Uri "$prom/api/v1/targets").data.activeTargets
            $jobs = $targets | ForEach-Object { $_.labels.job }
            $down = @($targets | Where-Object { $_.health -ne "up" })
            $missing = $expected | Where-Object { $jobs -notcontains $_ }
            $requiredDown = @($down | Where-Object { $required -contains $_.labels.job })
            if ($missing.Count -eq 0 -and $requiredDown.Count -eq 0) { break }
            Start-Sleep -Seconds 3
        } while ((Get-Date) -lt $deadline)
        foreach ($job in $expected) {
            Assert-True ($jobs -contains $job) "target не найден: $job"
        }
        $requiredDown = @($down | Where-Object { $required -contains $_.labels.job })
        Assert-True ($requiredDown.Count -eq 0) (
            "targets down: " + (($requiredDown | ForEach-Object { $_.labels.job }) -join ",")
        )
        $apiDown = @($down | Where-Object { $_.labels.job -eq "chessclass-api" })
        if ($apiDown.Count -gt 0) {
            Write-Host "    [info] chessclass-api down — базовый стек не запущен (не ошибка профиля)" `
                -ForegroundColor DarkYellow
        }
    }
    Check "правила загружены в Prometheus (12)" {
        $groups = (Invoke-RestMethod -Uri "$prom/api/v1/rules").data.groups
        $count = ($groups | ForEach-Object { $_.rules.Count } | Measure-Object -Sum).Sum
        Assert-True ($count -eq 12) "rules=$count"
    }
    Check "S-88 gauges email_outbox/retention видны в /metrics" {
        $metricNames = @(
            "chessclass_email_outbox_pending_total",
            "chessclass_email_outbox_oldest_pending_age_seconds",
            "chessclass_retention_archive_age_seconds",
            "chessclass_legal_holds_active_total",
            "chessclass_email_outbox_body_pending_scrub_total",
            "chessclass_retention_last_success_timestamp_seconds"
        )
        # Профиль можно проверять без базового стека; gauges отдаёт api.
        # Если api не запущен — это ответственность smoke базового стека
        # (покрытие — backend-тест test_email_outbox_and_retention_metrics).
        $apiTarget = (Invoke-RestMethod -Uri "$prom/api/v1/targets").data.activeTargets |
            Where-Object { $_.labels.job -eq "chessclass-api" } |
            Select-Object -First 1
        if (-not $apiTarget -or $apiTarget.health -ne "up") {
            Write-Host "    [info] chessclass-api down — gauges проверены backend-тестом" `
                -ForegroundColor DarkYellow
            return
        }
        $deadline = (Get-Date).AddSeconds(60)
        do {
            $missing = @()
            foreach ($metric in $metricNames) {
                $query = [uri]::EscapeDataString($metric)
                $response = Invoke-RestMethod -Uri "$prom/api/v1/query?query=$query"
                if ($response.data.result.Count -eq 0) {
                    $missing += $metric
                }
            }
            if ($missing.Count -eq 0) { return }
            Start-Sleep -Seconds 3
        } while ((Get-Date) -lt $deadline)
        throw "нет gauges в Prometheus: $($missing -join ', ')"
    }
    Check "Alertmanager связан с Prometheus" {
        # Service discovery Alertmanager также обновляется по интервалу.
        $deadline = (Get-Date).AddSeconds(90)
        $ams = @()
        do {
            $ams = @((Invoke-RestMethod -Uri "$prom/api/v1/alertmanagers").data.activeAlertmanagers)
            if ($ams.Count -ge 1) { return }
            Start-Sleep -Seconds 3
        } while ((Get-Date) -lt $deadline)
        Assert-True ($ams.Count -ge 1) "нет активных Alertmanager"
    }
    Check "маршруты Alertmanager: critical→telegram-critical+email, warning→telegram+email" {
        $container = "chessclass-prod-alertmanager"
        $critical = docker exec $container amtool config routes test `
            --config.file=/tmp/alertmanager.yml severity=critical alertname=ChessClassHighErrorRate component=api 2>&1
        $warning = docker exec $container amtool config routes test `
            --config.file=/tmp/alertmanager.yml severity=warning alertname=ChessClassDLQGrowth component=worker 2>&1
        Assert-True (($critical -join "`n") -match "telegram-critical") "critical: $critical"
        Assert-True (($critical -join "`n") -match "email") "critical без email: $critical"
        Assert-True (($warning -join "`n") -match "telegram") "warning: $warning"
        Assert-True (($warning -join "`n") -match "email") "warning без email: $warning"
    }
    Check "второй receiver (email) получает тестовый алерт" {
        # Уникальное имя: nflog Alertmanager переживает рестарт, и повторный
        # прогон с тем же alertname ждал бы repeat_interval вместо group_wait.
        $alertName = "ChessClassSelftest" + (Get-Date -Format "HHmmss")
        $start = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        $end = (Get-Date).ToUniversalTime().AddMinutes(30).ToString("yyyy-MM-ddTHH:mm:ssZ")
        docker exec chessclass-prod-alertmanager amtool alert add $alertName `
            severity=critical component=observability `
            --annotation=summary="S-87 selftest" `
            --annotation=description="Проверка второго receiver" `
            --start=$start --end=$end `
            --alertmanager.url=http://127.0.0.1:9093 2>&1 | Out-Null
        Assert-True ($LASTEXITCODE -eq 0) "amtool alert add exit=$LASTEXITCODE"
        # group_wait 30s + gossip; ждём до 120 с.
        $deadline = (Get-Date).AddSeconds(120)
        do {
            $sinkLogs = (docker logs $sinkName 2>&1) -join "`n"
            if ($sinkLogs -match [regex]::Escape($alertName)) { return }
            Start-Sleep -Seconds 3
        } while ((Get-Date) -lt $deadline)
        throw "email не получен за 120 с ($alertName)"
    }
    Check "логи Alertmanager маскируют bot token" {
        $deadline = (Get-Date).AddSeconds(60)
        $logs = ""
        do {
            $logs = (docker logs chessclass-prod-alertmanager 2>&1) -join "`n"
            if ($logs -match "bot<REDACTED>") { break }
            Start-Sleep -Seconds 3
        } while ((Get-Date) -lt $deadline)
        Assert-True ($logs -match "bot<REDACTED>") "нет bot<REDACTED> в логах"
        Assert-True (-not ($logs -match [regex]::Escape($fakeToken))) "raw token в логах"
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
    # Убираем только selftest-приёмник; профиль останавливаем, volumes сохраняем.
    docker rm -f $sinkName 2>&1 | Out-Null
    docker compose --env-file $EnvFile -f $Compose --profile observability `
        stop tempo otel-collector node-exporter prometheus alertmanager grafana 2>&1 | Out-Null
}

if ($script:failed -gt 0) {
    Write-Host "[obs-selftest] FAILED: $($script:failed)" -ForegroundColor Red
    exit 1
}
Write-Host "[obs-selftest] OK" -ForegroundColor Green
