# S-93: restore-test offsite-бэкапа в временный PostgreSQL (порт 5439).
# Скачивает последний *.dump.enc из S3 (или берёт -BackupFile), расшифровывает,
# поднимает chessclass-restore-test, восстанавливает, проверяет users/alembic.
param(
    [string]$BackupFile = "",
    [string]$BackupDir = $(if ($env:BACKUP_DIR) { $env:BACKUP_DIR } else { "backups" }),
    [string]$S3Endpoint = $env:BACKUP_S3_ENDPOINT,
    [string]$S3Bucket = $env:BACKUP_S3_BUCKET,
    [string]$S3Prefix = $(if ($env:BACKUP_S3_PREFIX) { $env:BACKUP_S3_PREFIX } else { "postgres" }),
    [string]$S3AccessKey = $env:BACKUP_S3_ACCESS_KEY,
    [string]$S3SecretKey = $env:BACKUP_S3_SECRET_KEY,
    [string]$EncryptionKey = $env:BACKUP_ENCRYPTION_KEY,
    [string]$StatusVolume = $env:BACKUP_STATUS_VOLUME,
    [string]$StatusFile = $env:BACKUP_STATUS_FILE,
    [string]$ExpectedAlembic = $env:BACKUP_EXPECTED_ALEMBIC,
    [int]$RestorePort = 5439,
    [switch]$KeepLocal
)

$ErrorActionPreference = "Stop"
$started = Get-Date

# v0.8.1: docker -v требует абсолютный host-path. Относительный BackupDir
# Docker трактует как named volume, и decrypt/download видят пустой каталог.
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$BackupDir = (Resolve-Path -LiteralPath $BackupDir -ErrorAction Stop).Path
if (-not $StatusFile) { $StatusFile = Join-Path $BackupDir "backup-status.json" }
$StatusFile = [System.IO.Path]::GetFullPath($StatusFile)
$statusDir = Split-Path -Parent $StatusFile
New-Item -ItemType Directory -Force -Path $statusDir | Out-Null

if (-not $EncryptionKey -or $EncryptionKey -notmatch '^[0-9a-fA-F]{32}$') {
    throw "BACKUP_ENCRYPTION_KEY должен быть 32 hex-символа"
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
        docker run --rm -v "${StatusVolume}:/srv/archive" -v "${statusDir}:/src:ro" `
            alpine sh -c "cp /src/$(Split-Path -Leaf $StatusFile) /srv/archive/backup-status.json" |
            Out-Null
    }
}

function Download-Latest {
    if (-not $S3Bucket -or -not $S3AccessKey -or -not $S3SecretKey) {
        throw "BackupFile не задан и S3 не настроен"
    }
    $leaf = $null
    if (Get-Command aws -ErrorAction SilentlyContinue) {
        $prefix = "s3://$S3Bucket/$($S3Prefix.Trim('/'))/"
        $args = @("s3", "ls", $prefix)
        if ($S3Endpoint) { $args = @("--endpoint-url", $S3Endpoint) + $args }
        $oldId = $env:AWS_ACCESS_KEY_ID
        $oldSecret = $env:AWS_SECRET_ACCESS_KEY
        $env:AWS_ACCESS_KEY_ID = $S3AccessKey
        $env:AWS_SECRET_ACCESS_KEY = $S3SecretKey
        try {
            $lines = & aws @args 2>$null
            $leaf = (
                $lines | Where-Object { $_ -match '\.dump\.enc$' } |
                    ForEach-Object { ($_ -split "\s+")[-1] } |
                    Sort-Object | Select-Object -Last 1
            )
            if (-not $leaf) { throw "в S3 нет *.dump.enc" }
            $args = @("s3", "cp", "${prefix}$leaf", (Join-Path $BackupDir $leaf))
            if ($S3Endpoint) { $args = @("--endpoint-url", $S3Endpoint) + $args }
            & aws @args | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "aws s3 cp failed" }
        } finally {
            $env:AWS_ACCESS_KEY_ID = $oldId
            $env:AWS_SECRET_ACCESS_KEY = $oldSecret
        }
    } elseif (Get-Command mc -ErrorAction SilentlyContinue) {
        if (-not $S3Endpoint) { throw "для mc нужен BACKUP_S3_ENDPOINT" }
        & mc alias set chessclass-backup $S3Endpoint $S3AccessKey $S3SecretKey | Out-Null
        $remote = "chessclass-backup/$S3Bucket/$($S3Prefix.Trim('/'))"
        $matches = & mc find $remote --name "*.dump.enc" 2>$null
        $leaf = (($matches | Sort-Object | Select-Object -Last 1) -split "/")[-1]
        if (-not $leaf) { throw "в S3 нет *.dump.enc" }
        & mc cp "$remote/$leaf" (Join-Path $BackupDir $leaf) | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "mc cp failed" }
    } else {
        if (-not $S3Endpoint) { throw "нужен aws/mc или BACKUP_S3_ENDPOINT" }
        docker run --rm --network $(if ($env:BACKUP_DOCKER_NETWORK) { $env:BACKUP_DOCKER_NETWORK } else { "chessclass-net" }) `
            -v "${BackupDir}:/backup" `
            -e AWS_ACCESS_KEY_ID=$S3AccessKey -e AWS_SECRET_ACCESS_KEY=$S3SecretKey `
            -e AWS_DEFAULT_REGION=$(if ($env:AWS_DEFAULT_REGION) { $env:AWS_DEFAULT_REGION } else { "us-east-1" }) `
            amazon/aws-cli --endpoint-url $S3Endpoint `
            s3 sync "s3://$S3Bucket/$($S3Prefix.Trim('/'))/" /backup/ | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "docker aws-cli s3 sync failed" }
        $leaf = (
            Get-ChildItem -LiteralPath $BackupDir -Filter "*.dump.enc" |
                Sort-Object LastWriteTime | Select-Object -Last 1
        ).Name
        if (-not $leaf) { throw "в S3 нет *.dump.enc" }
    }
    return (Join-Path $BackupDir $leaf)
}

$container = "chessclass-restore-test"
$status = Read-Status
$download = $null
$plain = $null
docker rm -f $container 2>$null | Out-Null

try {
    if (-not $BackupFile) { $BackupFile = Download-Latest; $download = $BackupFile }
    if (-not (Test-Path -LiteralPath $BackupFile)) { throw "backup not found: $BackupFile" }
    $BackupFile = (Resolve-Path -LiteralPath $BackupFile -ErrorAction Stop).Path
    $backupFileDir = Split-Path -Parent $BackupFile
    $plain = Join-Path $backupFileDir "$([IO.Path]::GetFileNameWithoutExtension($BackupFile)).dump"
    docker run --rm -v "${backupFileDir}:/backup" -e "BACKUP_KEY=$EncryptionKey" alpine/openssl `
        enc -d -aes-256-cbc -pbkdf2 -in "/backup/$(Split-Path -Leaf $BackupFile)" `
        -out "/backup/$(Split-Path -Leaf $plain)" -pass env:BACKUP_KEY | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "openssl decrypt failed" }

    docker run -d --rm --name $container `
        -e POSTGRES_PASSWORD=restore -e POSTGRES_DB=postgres `
        -p "127.0.0.1:${RestorePort}:5432" pgvector/pgvector:pg17 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "restore container failed" }
    $deadline = (Get-Date).AddSeconds(60)
    do {
        docker exec $container pg_isready -U postgres -d postgres 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    docker exec $container pg_isready -U postgres -d postgres 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "restore PostgreSQL не готов" }

    docker cp $plain "${container}:/tmp/restore.dump"
    if ($LASTEXITCODE -ne 0) { throw "docker cp failed" }
    docker exec $container pg_restore -U postgres -d postgres `
        --no-owner --no-privileges --exit-on-error /tmp/restore.dump 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "pg_restore failed" }

    $users = [int](docker exec $container psql -U postgres -d postgres -tAc `
        "select count(*) from users").Trim()
    $alembic = (docker exec $container psql -U postgres -d postgres -tAc `
        "select version_num from alembic_version").Trim()
    if ($users -lt 1) { throw "restore verification: users=0" }
    if (-not $alembic) { throw "restore verification: alembic_version empty" }
    if ($ExpectedAlembic -and $alembic -ne $ExpectedAlembic) {
        throw "alembic mismatch: $alembic != $ExpectedAlembic"
    }
    $status["last_restore_ok"] = $true
    $status["last_restore_timestamp"] = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $status["last_restore_file"] = Split-Path -Leaf $BackupFile
    $status["last_restore_users"] = $users
    $status["last_restore_alembic"] = $alembic
    $status.Remove("last_restore_error")
    Write-Status $status
    Write-Host "[restore-test] OK: users=$users alembic=$alembic"
} catch {
    $status["last_restore_ok"] = $false
    $status["last_restore_timestamp"] = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $status["last_restore_error"] = $_.Exception.Message
    Write-Status $status
    throw
} finally {
    docker rm -f $container 2>$null | Out-Null
    if (-not $KeepLocal) {
        if ($download) { Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue }
        if ($plain) { Remove-Item -LiteralPath $plain -Force -ErrorAction SilentlyContinue }
    }
}
