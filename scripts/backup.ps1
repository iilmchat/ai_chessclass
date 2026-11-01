# Бэкап БД ChessClass для Windows (S-38): pg_dump custom-format через
# docker exec + sha256 + retention. Запуск:
#   .\scripts\backup.ps1
#   .\scripts\backup.ps1 -Container chessclass-prod-db -BackupDir D:\backups\chessclass
param(
    [string]$Container = "chessclass-prod-db",
    [string]$BackupDir = "backups",
    [string]$User = "chess",
    [string]$Database = "chessclass",
    [int]$RetentionDays = 14
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$out = Join-Path $BackupDir "$Database-$stamp.dump"
$tmp = "/tmp/chessclass-$stamp.dump"

try {
    docker exec $Container pg_dump -U $User -d $Database -Fc -f $tmp
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }
    docker cp "${Container}:$tmp" $out
    if ($LASTEXITCODE -ne 0) { throw "docker cp failed" }
} finally {
    docker exec $Container rm -f $tmp 2>$null | Out-Null
}

$hash = (Get-FileHash -Algorithm SHA256 -Path $out).Hash.ToLowerInvariant()
"$hash  $(Split-Path $out -Leaf)" |
    Set-Content -Encoding ascii -Path "$out.sha256"

$size = [math]::Round((Get-Item $out).Length / 1MB, 2)
Write-Host "[backup] $out ($size MiB)"
Write-Host "[backup] sha256: $hash"

$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem -Path $BackupDir -Filter "$Database-*.dump*" |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    Remove-Item -Force
Write-Host "[backup] retention: files older than $RetentionDays days removed"
