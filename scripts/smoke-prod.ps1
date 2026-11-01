# ChessClass - smoke prod-стека (S-30/S-38).
# Пример:
#   .\scripts\smoke-prod.ps1 -WebBase https://localhost -EdgeBase https://localhost -SkipCertificateCheck
param(
    [string]$ApiBase = "http://127.0.0.1:8020",
    [string]$WebBase = "http://localhost:3200",
    [string]$EdgeBase = "",
    [switch]$SkipCertificateCheck
)

$ErrorActionPreference = "Stop"
$failed = 0
$webArgs = @{}
if ($SkipCertificateCheck) { $webArgs["SkipCertificateCheck"] = $true }

function Check([string]$Name, [scriptblock]$Probe) {
    try {
        & $Probe | Out-Null
        Write-Host "[ok]   $Name" -ForegroundColor Green
    } catch {
        Write-Host "[fail] $Name - $($_.Exception.Message)" -ForegroundColor Red
        $script:failed++
    }
}

Check "healthz (db+redis)" {
    $health = Invoke-RestMethod -Uri "$ApiBase/healthz" -TimeoutSec 10
    if ($health.status -ne "ok" -or -not $health.db -or -not $health.redis) {
        throw "unhealthy: $($health | ConvertTo-Json -Compress)"
    }
}

Check "readyz (migrations head)" {
    $ready = Invoke-RestMethod -Uri "$ApiBase/readyz" -TimeoutSec 10
    if ($ready.status -ne "ready") {
        throw "not ready: $($ready | ConvertTo-Json -Compress)"
    }
    if (-not $ready.db.migrationsUpToDate) {
        throw "migrations are not up to date: $($ready.db.revision) != $($ready.db.head)"
    }
}

Check "web (SPA)" {
    $page = Invoke-WebRequest -Uri "$WebBase/" -TimeoutSec 10 -UseBasicParsing @webArgs
    if ($page.StatusCode -ne 200) { throw "HTTP $($page.StatusCode)" }
    if ($page.Content -notmatch 'id="root"') { throw "SPA root not found" }
}

if ($EdgeBase) {
    Check "edge https healthz" {
        $health = Invoke-RestMethod -Uri "$EdgeBase/healthz" -TimeoutSec 10 @webArgs
        if ($health.status -ne "ok") { throw "edge healthz: $($health.status)" }
    }
    Check "edge HSTS/security headers" {
        $page = Invoke-WebRequest -Uri "$EdgeBase/" -TimeoutSec 10 -UseBasicParsing @webArgs
        if (-not $page.Headers["Strict-Transport-Security"]) {
            throw "HSTS header missing"
        }
        if ($page.Headers["X-Content-Type-Options"] -ne "nosniff") {
            throw "X-Content-Type-Options missing"
        }
    }
}

if ($failed -gt 0) {
    Write-Host "smoke: FAILED ($failed)" -ForegroundColor Red
    exit 1
}
Write-Host "smoke: OK" -ForegroundColor Green
