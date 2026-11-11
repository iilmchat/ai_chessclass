# Staging acceptance v0.8.1 (операционный чек-лист, не unit-тест).
#
# Проверяет staging API по боевому контуру: health/ready, admin login,
# JWKS (RS256), регистрацию ученика, backup-метрику и observability.
# Пароли/токены не выводятся. Секреты SMTP/S3 задаёт оператор в .env.staging.
#
# Пример:
#   .\scripts\staging-acceptance.ps1 `
#     -BaseUrl https://staging.example/api/v1 `
#     -AdminEmail admin@example.com -AdminPassword '<secret>' `
#     -TestStudentEmail accept-2026-11-11@example.com
#
# BaseUrl можно передать как origin (https://host) или как .../api/v1.
# Exit: 0 - все ok; 1 - есть warning; 2 - есть critical.
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$BaseUrl,
    [Parameter(Mandatory)][string]$AdminEmail,
    [Parameter(Mandatory)][string]$AdminPassword,
    [Parameter(Mandatory)][string]$TestStudentEmail,
    [string]$StudentPassword = "",
    [int]$TimeoutSec = 20,
    [string]$DbContainer = "chessclass-staging-db",
    [string]$DbUser = "chess",
    [string]$DbName = "chessclass",
    [switch]$SkipStudentRegistration,
    [switch]$RequireEmailOutbox
)

$ErrorActionPreference = "Stop"
$script:results = [System.Collections.Generic.List[object]]::new()
$script:exitCode = 0

function Add-Result {
    param(
        [string]$Check,
        [ValidateSet("OK", "WARN", "FAIL", "SKIP")][string]$Result,
        [string]$Details
    )
    $script:results.Add([pscustomobject]@{
        Check = $Check
        Result = $Result
        Details = $Details
    })
    if ($Result -eq "FAIL") { $script:exitCode = 2 }
    elseif ($Result -eq "WARN" -and $script:exitCode -lt 2) { $script:exitCode = 1 }
}

function Invoke-Api {
    param(
        [ValidateSet("GET", "POST")][string]$Method,
        [string]$Uri,
        [object]$Body = $null,
        [string]$Token = ""
    )
    $headers = @{}
    if ($Token) { $headers["Authorization"] = "Bearer $Token" }
    $params = @{
        Method = $Method
        Uri = $Uri
        Headers = $headers
        TimeoutSec = $TimeoutSec
        SkipHttpErrorCheck = $true
    }
    if ($null -ne $Body) {
        $params["ContentType"] = "application/json"
        $params["Body"] = ($Body | ConvertTo-Json -Compress)
    }
    try {
        $response = Invoke-WebRequest @params
        $json = $null
        if ($response.Content) {
            try { $json = $response.Content | ConvertFrom-Json } catch { $json = $null }
        }
        return [pscustomobject]@{
            Status = [int]$response.StatusCode
            Json = $json
            Text = [string]$response.Content
        }
    } catch {
        return [pscustomobject]@{
            Status = 0
            Json = $null
            Text = [string]$_.Exception.Message
        }
    }
}

function Get-ErrorCode($Json) {
    if ($null -eq $Json) { return "" }
    $code = $Json.code
    if ($code) { return " code=$code" }
    return ""
}

function Test-EmailOutbox {
    param([string]$Email)
    if ($SkipStudentRegistration) { return }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Add-Result "email_outbox" "SKIP" "docker CLI не найден; проверьте письмо у провайдера"
        return
    }
    $running = (& docker inspect -f "{{.State.Running}}" $DbContainer 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $running -ne "true") {
        Add-Result "email_outbox" "SKIP" "контейнер $DbContainer не запущен"
        return
    }
    $escaped = $Email.ToLowerInvariant().Replace("'", "''")
    $sql = "SELECT status FROM email_outbox WHERE recipient='$escaped' " +
        "ORDER BY created_at DESC LIMIT 1;"
    $status = (& docker exec $DbContainer psql -U $DbUser -d $DbName -tAc $sql 2>$null |
        Out-String).Trim()
    if ($status) {
        switch ($status) {
            "sent" {
                Add-Result "email_outbox" "OK" "status=sent"
                return
            }
            "pending" {
                Add-Result "email_outbox" "WARN" "status=pending; worker ещё не отправил"
                return
            }
            "failed" {
                Add-Result "email_outbox" "FAIL" "status=failed; смотрите last_error"
                return
            }
            default {
                Add-Result "email_outbox" "WARN" "неизвестный status=$status"
                return
            }
        }
    }
    $recentSql = "SELECT count(*) FROM email_outbox " +
        "WHERE status='sent' AND created_at > now() - interval '24 hours';"
    $recent = (& docker exec $DbContainer psql -U $DbUser -d $DbName -tAc $recentSql 2>$null |
        Out-String).Trim()
    $recentCount = 0
    [void][int]::TryParse($recent, [ref]$recentCount)
    if ($recentCount -gt 0) {
        Add-Result "email_outbox" "OK" (
            "нет строки test-email; sent за 24 ч=$recentCount " +
            "(verify-письмо идёт синхронно через SMTP)"
        )
        return
    }
    if ($RequireEmailOutbox) {
        Add-Result "email_outbox" "FAIL" (
            "нет строки для $Email; auth verify синхронный, " +
            "проверьте SMTP/провайдера и -RequireEmailOutbox"
        )
        return
    }
    Add-Result "email_outbox" "SKIP" (
        "нет строки для $Email; auth verify синхронный, " +
        "проверьте доставку у провайдера"
    )
}

if ($BaseUrl -notmatch '^https?://') {
    throw "BaseUrl должен начинаться с http:// или https://"
}
$base = $BaseUrl.TrimEnd('/')
if ($base -match '/api/v1$') {
    $api = $base
    $origin = $base -replace '/api/v1$', ''
} else {
    $origin = $base
    $api = "$base/api/v1"
}
Write-Host "[staging-acceptance] origin=$origin api=$api (секреты не выводятся)"

# 1. healthz
$health = Invoke-Api -Method GET -Uri "$origin/healthz"
if ($health.Status -eq 200 -and $health.Json.status -eq "ok") {
    Add-Result "healthz" "OK" "status=ok db=$($health.Json.db) redis=$($health.Json.redis)"
} else {
    Add-Result "healthz" "FAIL" (
        "HTTP $($health.Status) status=$($health.Json.status) " +
        "db=$($health.Json.db) redis=$($health.Json.redis)"
    )
}

# 2. readyz
$ready = Invoke-Api -Method GET -Uri "$origin/readyz"
$migrationsOk = $ready.Json.db.migrationsUpToDate -eq $true
if ($ready.Status -eq 200 -and $ready.Json.status -eq "ready" -and $migrationsOk) {
    Add-Result "readyz" "OK" (
        "version=$($ready.Json.version) revision=$($ready.Json.db.revision) " +
        "head=$($ready.Json.db.head)"
    )
} else {
    Add-Result "readyz" "FAIL" (
        "HTTP $($ready.Status) status=$($ready.Json.status) " +
        "migrationsUpToDate=$($ready.Json.db.migrationsUpToDate) " +
        "revision=$($ready.Json.db.revision) head=$($ready.Json.db.head)"
    )
}

# 3. admin login
$login = Invoke-Api -Method POST -Uri "$api/auth/login" -Body @{
    email = $AdminEmail
    password = $AdminPassword
}
$adminToken = $null
if ($login.Status -eq 200 -and $login.Json.accessToken) {
    $adminToken = [string]$login.Json.accessToken
    Add-Result "admin_login" "OK" (
        "HTTP 200 role=$($login.Json.user.role) " +
        "emailVerified=$($login.Json.user.emailVerified)"
    )
} else {
    Add-Result "admin_login" "FAIL" (
        "HTTP $($login.Status)$(Get-ErrorCode $login.Json)"
    )
}

# 4. JWKS
$jwks = Invoke-Api -Method GET -Uri "$api/auth/jwks"
$keys = @($jwks.Json.keys)
$kids = @($keys | ForEach-Object { $_.kid } | Where-Object { $_ })
if ($jwks.Status -eq 200 -and $keys.Count -gt 0 -and $kids.Count -gt 0) {
    Add-Result "jwks" "OK" "keys=$($keys.Count) kid=$($kids -join ',')"
} else {
    Add-Result "jwks" "FAIL" (
        "HTTP $($jwks.Status) keys=$($keys.Count); " +
        "нужен RS256/JWKS с kid"
    )
}

# 5. регистрация тестового ученика + outbox
if ($SkipStudentRegistration) {
    Add-Result "student_register" "SKIP" "-SkipStudentRegistration"
} else {
    $password = $StudentPassword
    if (-not $password) {
        $password = "Aa1!" + [guid]::NewGuid().ToString("N").Substring(0, 16)
    }
    if ($password.Length -lt 8) {
        Add-Result "student_register" "FAIL" "StudentPassword короче 8 символов"
    } else {
        $register = Invoke-Api -Method POST -Uri "$api/auth/register" -Body @{
            email = $TestStudentEmail
            password = $password
        }
        if ($register.Status -eq 201) {
            Add-Result "student_register" "OK" (
                "HTTP 201 id=$($register.Json.id) " +
                "emailVerified=$($register.Json.emailVerified)"
            )
        } elseif ($register.Status -eq 409) {
            Add-Result "student_register" "WARN" (
                "HTTP 409 email уже зарегистрирован; outbox проверяется по нему"
            )
        } else {
            Add-Result "student_register" "FAIL" (
                "HTTP $($register.Status)$(Get-ErrorCode $register.Json)"
            )
        }
        Test-EmailOutbox -Email $TestStudentEmail
    }
}

# 6. backup metric
$metrics = Invoke-Api -Method GET -Uri "$origin/metrics"
if ($metrics.Status -eq 200) {
    $backupMatch = [regex]::Match(
        $metrics.Text,
        "(?m)^chessclass_backup_last_success_timestamp_seconds\s+([0-9.]+)\s*$"
    )
    $pendingMatch = [regex]::Match(
        $metrics.Text,
        "(?m)^chessclass_email_outbox_pending_total\s+([0-9.]+)\s*$"
    )
    $backupTs = 0.0
    if ($backupMatch.Success) {
        [void][double]::TryParse(
            $backupMatch.Groups[1].Value,
            [System.Globalization.NumberStyles]::Float,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$backupTs
        )
    }
    $pending = -1
    if ($pendingMatch.Success) {
        [void][int]::TryParse($pendingMatch.Groups[1].Value, [ref]$pending)
    }
    if ($backupTs -gt 0) {
        Add-Result "backup_metric" "OK" (
            "last_success_ts=$([math]::Round($backupTs, 0)) " +
            "outbox_pending=$pending"
        )
    } else {
        Add-Result "backup_metric" "FAIL" (
            "chessclass_backup_last_success_timestamp_seconds отсутствует или 0"
        )
    }
    if ($pending -gt 0) {
        Add-Result "email_outbox_pending" "WARN" "pending_total=$pending"
    }
} else {
    Add-Result "backup_metric" "FAIL" "HTTP $($metrics.Status) /metrics"
}

# 7. observability summary + critical alerts
if (-not $adminToken) {
    Add-Result "observability" "FAIL" "нет admin JWT — summary недоступен"
} else {
    $summary = Invoke-Api -Method GET `
        -Uri "$api/admin/observability/summary" -Token $adminToken
    $alerts = Invoke-Api -Method GET `
        -Uri "$api/admin/observability/alerts" -Token $adminToken
    $critical = @()
    $warnings = @()
    if ($alerts.Status -eq 200) {
        $critical = @($alerts.Json | Where-Object { $_.severity -eq "critical" })
        $warnings = @($alerts.Json | Where-Object { $_.severity -eq "warning" })
    }
    if ($summary.Status -ne 200) {
        Add-Result "observability" "FAIL" (
            "summary HTTP $($summary.Status)$(Get-ErrorCode $summary.Json)"
        )
    } elseif ($critical.Count -gt 0) {
        $codes = ($critical | ForEach-Object { $_.code }) -join ","
        Add-Result "observability" "FAIL" "critical alerts: $codes"
    } elseif ($summary.Json.db -ne $true -or $summary.Json.redis -ne $true) {
        Add-Result "observability" "FAIL" (
            "summary db=$($summary.Json.db) redis=$($summary.Json.redis)"
        )
    } elseif ($warnings.Count -gt 0) {
        $codes = ($warnings | ForEach-Object { $_.code }) -join ","
        Add-Result "observability" "WARN" (
            "warning alerts: $codes; failedJobs=$($summary.Json.failedJobs)"
        )
    } elseif ($alerts.Status -ne 200) {
        Add-Result "observability" "WARN" (
            "summary ok; alerts HTTP $($alerts.Status)"
        )
    } else {
        Add-Result "observability" "OK" (
            "alerts=0 failedJobs=$($summary.Json.failedJobs) " +
            "diskFreeGb=$($summary.Json.diskFreeGb)"
        )
    }
}

$table = $script:results | Format-Table -AutoSize | Out-String
Write-Host $table
Write-Host ("[staging-acceptance] exit={0} (0=ok, 1=warning, 2=critical)" -f $script:exitCode)
exit $script:exitCode
