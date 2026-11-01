# Безопасная проверка восстановления бэкапа (S-38): restore во временную БД,
# проверка users/alembic_version, затем drop. Production-БД не затрагивается.
# Запуск:
#   .\scripts\restore-test.ps1 -BackupFile .\backups\chessclass-....dump
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$Container = "chessclass-prod-db",
    [string]$User = "chess",
    [string]$RestoreDb = "chessclass_restore"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $BackupFile)) { throw "backup not found: $BackupFile" }

$shaFile = "$BackupFile.sha256"
if (Test-Path $shaFile) {
    $expected = ((Get-Content $shaFile -First 1) -split "\s+")[0].ToLowerInvariant()
    $actual = (Get-FileHash -Algorithm SHA256 -Path $BackupFile).Hash.ToLowerInvariant()
    if ($expected -ne $actual) { throw "sha256 mismatch: $expected != $actual" }
    Write-Host "[restore] sha256 OK"
}

$inside = "/tmp/chessclass-restore-$(Get-Random).dump"
docker cp $BackupFile "${Container}:$inside"
if ($LASTEXITCODE -ne 0) { throw "docker cp failed" }

try {
    docker exec $Container dropdb --if-exists -U $User $RestoreDb
    docker exec $Container createdb -U $User $RestoreDb
    if ($LASTEXITCODE -ne 0) { throw "createdb failed" }

    if ($BackupFile -like "*.dump") {
        docker exec $Container pg_restore -U $User -d $RestoreDb --no-owner --no-privileges $inside
        if ($LASTEXITCODE -ne 0) { throw "pg_restore failed" }
    } elseif ($BackupFile -like "*.sql.gz") {
        docker exec $Container sh -c "gunzip -c '$inside' | psql -U '$User' -d '$RestoreDb'"
        if ($LASTEXITCODE -ne 0) { throw "psql restore failed" }
    } else {
        docker exec $Container sh -c "psql -U '$User' -d '$RestoreDb' -f '$inside'"
        if ($LASTEXITCODE -ne 0) { throw "psql restore failed" }
    }

    $usersRaw = (docker exec $Container psql -U $User -d $RestoreDb -tAc "select count(*) from users").Trim()
    $rev = (docker exec $Container psql -U $User -d $RestoreDb -tAc "select version_num from alembic_version").Trim()
    $users = [int]$usersRaw
    if ($users -lt 1) { throw "restore verification: users=0" }
    if ([string]::IsNullOrWhiteSpace($rev)) { throw "restore verification: alembic_version empty" }
    Write-Host "[restore] OK: users=$users alembic=$rev"
} finally {
    docker exec $Container dropdb --if-exists -U $User $RestoreDb 2>$null | Out-Null
    docker exec $Container rm -f $inside 2>$null | Out-Null
}
