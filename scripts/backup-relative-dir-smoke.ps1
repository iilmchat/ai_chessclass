# v0.8.1: smoke для относительного -BackupDir (Windows docker bind mount).
# Проверяет, что backup-offsite.ps1 резолвит путь в абсолютный до docker -v.
# Запуск: .\scripts\backup-relative-dir-smoke.ps1
param(
    [string]$BackupDir = ".\backups-v081-smoke\nested"
)

$ErrorActionPreference = "Stop"
if ([System.IO.Path]::IsPathRooted($BackupDir)) {
    throw "smoke требует относительный -BackupDir, получен: $BackupDir"
}
$existed = Test-Path -LiteralPath $BackupDir
$json = $null
try {
    $out = & (Join-Path $PSScriptRoot "backup-offsite.ps1") `
        -BackupDir $BackupDir -DryRun
    $json = ($out | Out-String).Trim() | ConvertFrom-Json
    if ($json.status -ne "dry-run") { throw "ожидался status=dry-run" }
    if (-not $json.mount_is_absolute) {
        throw "BackupDir не абсолютный: $($json.backup_dir)"
    }
    if (-not [System.IO.Path]::IsPathRooted($json.backup_dir)) {
        throw "backup_dir не rooted: $($json.backup_dir)"
    }
    if ($json.docker_mount -notmatch '^(?:[A-Za-z]:\\|/)') {
        throw "docker_mount не абсолютный: $($json.docker_mount)"
    }
    Write-Host "[backup-relative-dir-smoke] OK: $($json.docker_mount)"
} finally {
    if ($json -and -not $existed -and (Test-Path -LiteralPath $json.backup_dir)) {
        $parent = Split-Path -Parent $json.backup_dir
        Remove-Item -LiteralPath $json.backup_dir -Recurse -Force -ErrorAction SilentlyContinue
        if ($parent -and (Test-Path -LiteralPath $parent) -and
            -not (Get-ChildItem -LiteralPath $parent -Force)) {
            Remove-Item -LiteralPath $parent -Force -ErrorAction SilentlyContinue
        }
    }
}
