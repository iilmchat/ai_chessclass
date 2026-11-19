#!/usr/bin/env bash
# KI-004: Linux-версия offsite-бэкапа PostgreSQL → dump → AES-256 → S3/MinIO.
# Совместима с backup-offsite.ps1: тот же openssl (aes-256-cbc/pbkdf2/salt)
# и тот же формат backup-status.json, поэтому restore-test работает с обоими.
#
# Запуск:
#   BACKUP_S3_BUCKET=... BACKUP_ENCRYPTION_KEY=<32 hex> \
#     bash scripts/backup-offsite.sh
# Переменные: BACKUP_DB_CONTAINER, POSTGRES_USER/POSTGRES_DB, BACKUP_DIR,
#   BACKUP_S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY, BACKUP_S3_PREFIX,
#   BACKUP_ENCRYPTION_KEY, BACKUP_DOCKER_NETWORK, BACKUP_STATUS_FILE.
set -euo pipefail
umask 077

CONTAINER="${BACKUP_DB_CONTAINER:-chessclass-prod-db}"
USER="${POSTGRES_USER:-chess}"
DB="${POSTGRES_DB:-chessclass}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-}"
S3_BUCKET="${BACKUP_S3_BUCKET:-}"
S3_PREFIX="${BACKUP_S3_PREFIX:-postgres}"
S3_ACCESS_KEY="${BACKUP_S3_ACCESS_KEY:-}"
S3_SECRET_KEY="${BACKUP_S3_SECRET_KEY:-}"
NETWORK="${BACKUP_DOCKER_NETWORK:-chessclass-net}"
STATUS_FILE="${BACKUP_STATUS_FILE:-$BACKUP_DIR/backup-status.json}"

if [[ "${1:-}" == "--dry-run" ]]; then
    printf '{"status":"dry-run","backup_dir":"%s","container":"%s","bucket":"%s"}\n' \
        "$BACKUP_DIR" "$CONTAINER" "$S3_BUCKET"
    exit 0
fi

if [[ ! "$BACKUP_ENCRYPTION_KEY" =~ ^[0-9a-fA-F]{32}$ ]]; then
    echo "backup-offsite: BACKUP_ENCRYPTION_KEY должен быть 32 hex-символа" >&2
    exit 2
fi
if [[ -z "$S3_BUCKET" || -z "$S3_ACCESS_KEY" || -z "$S3_SECRET_KEY" ]]; then
    echo "backup-offsite: BACKUP_S3_BUCKET/ACCESS_KEY/SECRET_KEY обязательны" >&2
    exit 2
fi

started=$(date +%s)
mkdir -p "$BACKUP_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BASE="${DB}-${STAMP}"
DUMP="$BACKUP_DIR/${BASE}.dump"
ENC="${DUMP}.enc"
TMP_DIR=$(mktemp -d)
trap 'rm -f "$DUMP" "$ENC.part"; rm -rf "$TMP_DIR"' EXIT

# 1. Дамп из контейнера (как в backup.ps1 — через docker exec).
docker exec "$CONTAINER" pg_dump -U "$USER" -d "$DB" -Fc -f "/tmp/${BASE}.dump"
docker cp "${CONTAINER}:/tmp/${BASE}.dump" "$DUMP"

# 2. Шифрование — тот же вызов openssl, что и в PowerShell-версии.
docker run --rm -v "${BACKUP_DIR}:/backup" -e "BACKUP_KEY=${BACKUP_ENCRYPTION_KEY}" \
    alpine/openssl enc -aes-256-cbc -pbkdf2 -salt \
    -in "/backup/${BASE}.dump" -out "/backup/${BASE}.dump.enc" \
    -pass env:BACKUP_KEY

SHA=$(sha256sum "$ENC" | cut -d' ' -f1)
SIZE=$(stat -c%s "$ENC" 2>/dev/null || wc -c < "$ENC")

# 3. Загрузка в S3 через docker aws-cli (на хосте не нужен aws/mc).
REMOTE="s3://${S3_BUCKET}/${S3_PREFIX#/}/${BASE}.dump.enc"
docker run --rm --network "$NETWORK" \
    -v "${ENC}:/backup/${BASE}.dump.enc:ro" \
    -e AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
    -e AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
    -e AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
    amazon/aws-cli ${S3_ENDPOINT:+--endpoint-url "$S3_ENDPOINT"} \
    s3 cp "/backup/${BASE}.dump.enc" "$REMOTE"

duration=$(( $(date +%s) - started ))
printf '{"status":"ok","size_bytes":"%s","sha256":"%s","duration_s":"%s","s3_path":"%s","local_path":"%s","encrypted":true}\n' \
    "$SIZE" "$SHA" "$duration" "$REMOTE" "$ENC"

printf '{"last_success_timestamp":%s,"last_backup_file":"%s","last_backup_sha256":"%s","last_backup_size_bytes":%s,"last_backup_s3_path":"%s","last_backup_duration_s":%s}\n' \
    "$(date +%s)" "${BASE}.dump.enc" "$SHA" "$SIZE" "$REMOTE" "$duration" > "$STATUS_FILE"
