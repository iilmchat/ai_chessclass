# S-88: проверка срока действия TLS-сертификатов ChessClass.
#
# По умолчанию проверяются:
#   deploy/internal-certs/*.crt  — внутренний CA, Tempo, collector (mTLS);
#   deploy/certs/*.pem           — edge TLS (fullchain/privkey; ключи пропускаются);
#   deploy/nginx/**/*.crt|*.pem  — дополнительные сертификаты edge (если есть).
#
# Пороги: < WarningDays (30) — warning, < CriticalDays (7) — critical.
# Exit code: 0 — все ok, 1 — есть warning, 2 — есть critical/нечитаемый.
# При warning/critical и заданных TELEGRAM_BOT_TOKEN + TELEGRAM_ALERT_CHAT_ID
# отправляется сообщение в Telegram (токен не печатается).
#
# Запуск:
#   .\scripts\check-cert-expiry.ps1
#   .\scripts\check-cert-expiry.ps1 -Paths deploy/certs -NoTelegram
#   .\scripts\check-cert-expiry.ps1 -Paths .\tmp\cert.crt -WarningDays 30 -CriticalDays 7
param(
    [string[]]$Paths = @(),
    [string]$Root = ".",
    [int]$WarningDays = 30,
    [int]$CriticalDays = 7,
    [switch]$NoTelegram,
    [string]$TelegramApiBase = ""
)

$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path -LiteralPath $Root).Path

function Get-DisplayPath {
    param([string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    $base = $rootPath.TrimEnd("\", "/") + [IO.Path]::DirectorySeparatorChar
    if ($full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
        return $full.Substring($base.Length)
    }
    return $full
}

function Get-CertificateFile {
    param([string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    if ([IO.Path]::GetFileName($full) -match "(?i)key") {
        return $null
    }
    $extension = [IO.Path]::GetExtension($full).ToLowerInvariant()
    if ($extension -notin @(".crt", ".pem", ".cer")) {
        return $null
    }
    return $full
}

function Get-CertificateFiles {
    $candidates = [System.Collections.Generic.List[string]]::new()
    if ($Paths.Count -gt 0) {
        foreach ($item in $Paths) {
            $full = if ([IO.Path]::IsPathRooted($item)) {
                $item
            } else {
                Join-Path $rootPath $item
            }
            if (-not (Test-Path -LiteralPath $full)) {
                throw "путь не найден: $item"
            }
            $resolved = (Resolve-Path -LiteralPath $full).Path
            if (Test-Path -LiteralPath $resolved -PathType Container) {
                Get-ChildItem -LiteralPath $resolved -Recurse -File -ErrorAction SilentlyContinue |
                    ForEach-Object { $candidates.Add($_.FullName) }
            } else {
                $candidates.Add($resolved)
            }
        }
    } else {
        $defaults = @(
            @{ Dir = "deploy/internal-certs"; Recurse = $false },
            @{ Dir = "deploy/certs"; Recurse = $false },
            @{ Dir = "deploy/nginx"; Recurse = $true }
        )
        foreach ($spec in $defaults) {
            $directory = Join-Path $rootPath $spec.Dir
            if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
                continue
            }
            $items = if ($spec.Recurse) {
                Get-ChildItem -LiteralPath $directory -Recurse -File -ErrorAction SilentlyContinue
            } else {
                Get-ChildItem -LiteralPath $directory -File -ErrorAction SilentlyContinue
            }
            foreach ($item in $items) {
                $candidates.Add($item.FullName)
            }
        }
    }

    $files = foreach ($candidate in ($candidates | Sort-Object -Unique)) {
        $certFile = Get-CertificateFile -Path $candidate
        if ($certFile) { $certFile }
    }
    return @($files)
}

function Get-CertificateNotAfter {
    param([string]$Path)
    # .NET читает первый сертификат из PEM (в fullchain — leaf); на Windows
    # PowerShell 5.1/DotNet работает без внешних зависимостей.
    try {
        $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($Path)
        return $cert.NotAfter.ToUniversalTime()
    } catch {
        try {
            $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::CreateFromPemFile($Path)
            return $cert.NotAfter.ToUniversalTime()
        } catch {
            # Fallback для экзотических PEM: openssl в контейнере (KI-001: только
            # alpine/openssl, без доступа к чужим контейнерам).
            $directory = Split-Path -Parent $Path
            $leaf = Split-Path -Leaf $Path
            $out = docker run --rm -v "${directory}:/certs:ro" alpine/openssl `
                x509 -in "/certs/$leaf" -noout -enddate 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "не удалось прочитать сертификат"
            }
            $line = ($out -join "`n")
            if ($line -notmatch "notAfter=(.+)") {
                throw "openssl не вернул notAfter"
            }
            return [DateTime]::ParseExact(
                $Matches[1].Trim(),
                "MMM d HH:mm:ss yyyy 'GMT'",
                [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::AssumeUniversal -bor
                    [Globalization.DateTimeStyles]::AdjustToUniversal
            )
        }
    }
}

$files = Get-CertificateFiles
$rows = [System.Collections.Generic.List[object]]::new()
foreach ($file in $files) {
    $display = Get-DisplayPath -Path $file
    try {
        $notAfter = Get-CertificateNotAfter -Path $file
        $days = [math]::Floor(($notAfter - [DateTime]::UtcNow).TotalDays)
        $status = if ($days -lt $CriticalDays) {
            "critical"
        } elseif ($days -lt $WarningDays) {
            "warning"
        } else {
            "ok"
        }
        $rows.Add([pscustomobject]@{
            Path = $display
            DaysLeft = $days
            DaysText = [string]$days
            Status = $status
        })
    } catch {
        Write-Warning "[cert-expiry] ${display}: $($_.Exception.Message)"
        $rows.Add([pscustomobject]@{
            Path = $display
            DaysLeft = $null
            DaysText = "n/a"
            Status = "critical"
        })
    }
}

$rank = @{ critical = 0; warning = 1; ok = 2 }
$rows = @($rows | Sort-Object `
    @{ Expression = { $rank[$_.Status] } }, `
    @{ Expression = { if ($null -ne $_.DaysLeft) { $_.DaysLeft } else { -999999 } } })

$critical = @($rows | Where-Object { $_.Status -eq "critical" }).Count
$warning = @($rows | Where-Object { $_.Status -eq "warning" }).Count
$ok = @($rows | Where-Object { $_.Status -eq "ok" }).Count

Write-Host "[cert-expiry] root: $rootPath"
if ($rows.Count -eq 0) {
    Write-Host "[cert-expiry] сертификаты не найдены — пропуск (каталоги могут быть пусты в CI)"
    exit 0
}

Write-Host ""
Write-Host ("{0,-56} {1,10}  {2}" -f "cert_path", "days_left", "status")
Write-Host ("{0,-56} {1,10}  {2}" -f ("-" * 56), ("-" * 10), ("-" * 7))
foreach ($row in $rows) {
    $color = switch ($row.Status) {
        "critical" { "Red" }
        "warning" { "Yellow" }
        default { "Green" }
    }
    Write-Host ("{0,-56} {1,10}  {2}" -f $row.Path, $row.DaysText, $row.Status) `
        -ForegroundColor $color
}
Write-Host ""
Write-Host ("[cert-expiry] ok=$ok warning=$warning critical=$critical " +
    "(порог: <$WarningDays warning, <$CriticalDays critical)")

$exitCode = if ($critical -gt 0) { 2 } elseif ($warning -gt 0) { 1 } else { 0 }

if ($exitCode -ne 0 -and -not $NoTelegram) {
    $token = $env:TELEGRAM_BOT_TOKEN
    $chatId = $env:TELEGRAM_ALERT_CHAT_ID
    if ($token -and $chatId) {
        $base = if ($TelegramApiBase) {
            $TelegramApiBase
        } elseif ($env:TELEGRAM_API_BASE) {
            $env:TELEGRAM_API_BASE
        } else {
            "https://api.telegram.org"
        }
        $base = $base.TrimEnd("/")
        $lines = @(
            "[cert-expiry] $(if ($exitCode -eq 2) { 'CRITICAL' } else { 'WARNING' }): " +
                "critical=$critical warning=$warning"
        )
        foreach ($row in ($rows | Where-Object { $_.Status -ne "ok" } | Select-Object -First 15)) {
            $lines += "$($row.Path): $($row.DaysText) дн. ($($row.Status))"
        }
        $text = $lines -join "`n"
        if ($text.Length -gt 3900) {
            $text = $text.Substring(0, 3900) + "`n…"
        }
        try {
            Invoke-RestMethod -Method Post -Uri "$base/bot$token/sendMessage" `
                -Body @{ chat_id = $chatId; text = $text } -TimeoutSec 15 | Out-Null
            Write-Host "[cert-expiry] Telegram: отправлено"
        } catch {
            # Не печатаем exception: в URL мог попасть токен.
            Write-Warning "[cert-expiry] Telegram: не отправлено (токен/chat_id/egress)"
        }
    } else {
        Write-Host "[cert-expiry] Telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_ALERT_CHAT_ID не заданы — пропуск"
    }
}

switch ($exitCode) {
    2 { exit 2 }
    1 { exit 1 }
    default { exit 0 }
}
