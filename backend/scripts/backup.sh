#!/usr/bin/env bash
# Бэкап БД ChessClass (Design §15.3): pg_dump через docker exec, gzip,
# retention 14 дней. Запуск: bash backend/scripts/backup.sh
set -euo pipefail

CONTAINER=${1:-chessclass-prod-db}
USER=${POSTGRES_USER:-chess}
DB=${POSTGRES_DB:-chessclass}
BACKUP_DIR=${2:-backups}
RETENTION_DAYS=14

mkdir -p "$BACKUP_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$BACKUP_DIR/${DB}-${STAMP}.sql.gz"

docker exec "$CONTAINER" pg_dump -U "$USER" -d "$DB" | gzip > "$OUT"
sha256sum "$OUT" > "$OUT.sha256"
echo "backup: $OUT ($(du -h "$OUT" | cut -f1))"

# ретеншен: удаляем файлы старше RETENTION_DAYS
find "$BACKUP_DIR" -name "${DB}-*.sql.gz*" -mtime "+$RETENTION_DAYS" -delete
echo "retention: файлы старше $RETENTION_DAYS дней удалены"
