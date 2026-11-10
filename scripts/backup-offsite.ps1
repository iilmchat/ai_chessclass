# S-93: offsite-бэкап PostgreSQL → gzip/aes → S3/MinIO.
# Секреты только из env/параметров; ключ/DSN не логируются.
#
# Запуск (prod):
#   .\scripts\backup-offsite.ps1 -Container chessclass-prod-db `
#     -StatusVolume chessclass_prod_archive
# Переменные: BACKUP_S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY,
#             BACKUP_ENCRYPTION_KEY (32 hex), BACKUP_S3_PREFIX,
#             BACKUP_DOCKER_NETWORK (для docker-fallback mc).
param(
    [string]$Container = $env:BACKUP_DB_CONTAINER,
    [string]$User = $env:POSTGRES_USER,
    [string]$Database = $env:POSTGRES_DB,
    [string]$DatabaseUrl = $env:BACKUP_DATABASE_URL,
    [string]$BackupDir = $(if ($env:BACKUP_DIR) { $env:BACKUP_DIR } else { "backups" }),
    [string]$S3Endpoint = $env:BACKUP_S3_ENDPOINT,
    [string]$S3Bucket = $env:BACKUP_S3_BUCKET,
    [string]$S3Prefix = $(if ($env:BACKUP_S3_PREFIX) { $env:BACKUP_S3_PREFIX } else { "postgres" }),
    [string]$S3AccessKey = $env:BACKUP_S3_ACCESS_KEY,
    [string]$S3SecretKey = $env:BACKUP_S3_SECRET_KEY,
    [string]$EncryptionKey = $env:BACKUP_ENCRYPTION_KEY,
    [string]$Network = $(if ($env:BACKUP_DOCKER_NETWORK) { $env:BACKUP_DOCKER_NETWORK } else { "chessclass-net" }),
    [string]$StatusVolume = $env:BACKUP_STATUS_VOLUME,
    [string]$StatusFile = $env:BACKUP_STATUS_FILE,
    [switch]$KeepLocal,
    [switch]$SkipUpload
)

$ErrorActionPreference = "Stop"
$started = Get-Date
if (-not $Container) { $Container = "chessclass-prod-db" }
if (-not $User) { $User = "chess" }
if (-not $Database) { $Database = "chessclass" }
if (-not $StatusFile) { $StatusFile = Join-Path $BackupDir "backup-status.json" }
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

if (-not $EncryptionKey -or $EncryptionKey -notmatch '^[0-9a-fA-F]{32}$') {
    throw "BACKUP_ENCRYPTION_KEY должен быть 32 hex-символа"
}
if (-not $SkipUpload -and (-not $S3Bucket -or -not $S3AccessKey -or -not $S3SecretKey)) {
    throw "S3 не настроен: нужны BACKUP_S3_BUCKET/ACCESS_KEY/SECRET_KEY"
}

function Read-Status {
    if ($StatusVolume) {
        $volumeJson = (
            docker run --rm -v "${StatusVolume}:/srv/archive" alpine `
                cat /srv/archive/backup-status.json 2>$null
        ) -join "`n"
        if ($volumeJson.Trim()) {
            try { return ($volumeJson | ConvertFrom-Json -AsHashtable) } catch {}
        }
    }
    if (-not (Test-Path -LiteralPath $StatusFile)) { return @{} }
    try {
        return (Get-Content -Raw -LiteralPath $StatusFile | ConvertFrom-Json -AsHashtable)
    } catch {
        return @{}
    }
}

function Write-Status([hashtable]$Data) {
    $json = $Data | ConvertTo-Json -Compress
    Set-Content -LiteralPath $StatusFile -Value $json -Encoding utf8
    if ($StatusVolume) {
        $absBackupDir = (Resolve-Path -LiteralPath $BackupDir).Path
        docker run --rm -v "${StatusVolume}:/srv/archive" -v "${absBackupDir}:/src:ro" `
            alpine sh -c "cp /src/$(Split-Path -Leaf $StatusFile) /srv/archive/backup-status.json" |
            Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "[backup-offsite] не удалось записать статус в volume $StatusVolume"
        }
    }
}

function Upload-S3([string]$File) {
    $leaf = Split-Path -Leaf $File
    $remote = "s3://$S3Bucket/$($S3Prefix.Trim('/'))/$leaf"
    if (Get-Command aws -ErrorAction SilentlyContinue) {
        $args = @("s3", "cp", $File, $remote)
        if ($S3Endpoint) { $args = @("--endpoint-url", $S3Endpoint) + $args }
        $oldId = $env:AWS_ACCESS_KEY_ID
        $oldSecret = $env:AWS_SECRET_ACCESS_KEY
        $env:AWS_ACCESS_KEY_ID = $S3AccessKey
        $env:AWS_SECRET_ACCESS_KEY = $S3SecretKey
        try { & aws @args | Out-Null } finally {
            $env:AWS_ACCESS_KEY_ID = $oldId
            $env:AWS_SECRET_ACCESS_KEY = $oldSecret
        }
        if ($LASTEXITCODE -ne 0) { throw "aws s3 cp failed" }
        return $remote
    }
    if (Get-Command mc -ErrorAction SilentlyContinue) {
        & mc alias set chessclass-backup $S3Endpoint $S3AccessKey $S3SecretKey | Out-Null
        & mc cp $File "chessclass-backup/$S3Bucket/$($S3Prefix.Trim('/'))/$leaf" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "mc cp failed" }
        return $remote
    }
    if (-not $S3Endpoint) { throw "нужен aws/mc или BACKUP_S3_ENDPOINT для docker aws-cli" }
    $absFile = (Resolve-Path -LiteralPath $File).Path
    docker run --rm --network $Network -v "${absFile}:/backup/${leaf}:ro" `
        -e AWS_ACCESS_KEY_ID=$S3AccessKey -e AWS_SECRET_ACCESS_KEY=$S3SecretKey `
        -e AWS_DEFAULT_REGION=$(if ($env:AWS_DEFAULT_REGION) { $env:AWS_DEFAULT_REGION } else { "us-east-1" }) `
        amazon/aws-cli --endpoint-url $S3Endpoint `
        s3 cp "/backup/$leaf" "s3://$S3Bucket/$($S3Prefix.Trim('/'))/$leaf" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "docker aws-cli s3 cp failed" }
    return $remote
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$base = "$Database-$stamp"
$dump = Join-Path $BackupDir "$base.dump"
$enc = "$dump.enc"
$tmp = "/tmp/$base.dump"
$status = Read-Status

try {
    if ($DatabaseUrl) {
        docker run --rm --add-host host.docker.internal:host-gateway `
            -v "${BackupDir}:/backup" postgres:17 `
            pg_dump $DatabaseUrl -Fc -f "/backup/$base.dump" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "pg_dump (DatabaseUrl) failed" }
    } else {
        docker exec $Container pg_dump -U $User -d $Database -Fc -f $tmp
        if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }
        docker cp "${Container}:$tmp" $dump | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "docker cp failed" }
    }

    docker run --rm -v "${BackupDir}:/backup" -e "BACKUP_KEY=$EncryptionKey" alpine/openssl `
        enc -aes-256-cbc -pbkdf2 -salt -in "/backup/$base.dump" `
        -out "/backup/$base.dump.enc" -pass env:BACKUP_KEY | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "openssl encrypt failed" }

    $sha = (Get-FileHash -Algorithm SHA256 -Path $enc).Hash.ToLowerInvariant()
    $size = (Get-Item $enc).Length
    $remote = if ($SkipUpload) { $null } else { Upload-S3 $enc }
    $duration = [math]::Round(((Get-Date) - $started).TotalSeconds, 2)
    $status["last_success_timestamp"] = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $status["last_backup_file"] = (Split-Path -Leaf $enc)
    $status["last_backup_sha256"] = $sha
    $status["last_backup_size_bytes"] = $size
    $status["last_backup_s3_path"] = $remote
    $status["last_backup_duration_s"] = $duration
    $status.Remove("last_failure_timestamp")
    $status.Remove("last_error")
    Write-Status $status
    $result = @{
        status = "ok"
        size_bytes = $size
        sha256 = $sha
        duration_s = $duration
        s3_path = $remote
        local_path = $enc
        encrypted = $true
    } | ConvertTo-Json -Compress
    Write-Output $result
} catch {
    $status["last_failure_timestamp"] = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $status["last_error"] = $_.Exception.Message
    Write-Status $status
    throw
} finally {
    if (-not $DatabaseUrl) {
        docker exec $Container rm -f $tmp 2>$null | Out-Null
    }
    if (-not $KeepLocal) {
        Remove-Item -LiteralPath $dump, $enc -Force -ErrorAction SilentlyContinue
    }
}
