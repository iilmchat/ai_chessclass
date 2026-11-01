# Регистрация nightly-бэкапа в Windows Task Scheduler (S-38).
# Требует запуска от администратора. Запуск:
#   .\scripts\install-backup-task.ps1 -BackupDir D:\backups\chessclass
param(
    [string]$Container = "chessclass-prod-db",
    [string]$BackupDir = "backups",
    [int]$RetentionDays = 14,
    [string]$TaskName = "ChessClassBackup",
    [string]$At = "03:00"
)

$ErrorActionPreference = "Stop"
$scriptPath = Join-Path $PSScriptRoot "backup.ps1"
$pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $pwsh) { $pwsh = (Get-Command powershell).Source }

$action = New-ScheduledTaskAction -Execute $pwsh `
    -Argument "-NoProfile -NonInteractive -File `"$scriptPath`" -Container `"$Container`" -BackupDir `"$BackupDir`" -RetentionDays $RetentionDays"
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -RunLevel Highest -Force | Out-Null

Write-Host "[backup] task '$TaskName' registered daily at $At"
Write-Host "[backup] script: $scriptPath"
