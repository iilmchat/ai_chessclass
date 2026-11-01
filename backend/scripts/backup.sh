#!/usr/bin/env bash
# Бэкап БД ChessClass (Design §15.3, S-38): pg_dump через docker exec,
# gzip, sha256, retention 14 дней. Запуск:
#   BACKUP_DIR=/var/backups/chessclass bash backend/scripts/backup.sh
set -euo pipefail
umask 077

CONTAINER=${1:-chessclass-prod-db}
USER=${POSTGRES_USER:-chess}
DB=${POSTGRES_DB:-chessclass}
BACKUP_DIR=${2:-${BACKUP_DIR:-backups}}
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-14}

mkdir -p "$BACKUP_DIR"
LOCK="$BACKUP_DIR/.backup.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
    echo "backup: уже выполняется ($LOCK)" >&2
    exit 1
fi
trap 'rm -rf "$LOCK"' EXIT

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$BACKUP_DIR/${DB}-${STAMP}.sql.gz"
TMP="$OUT.part"

cleanup() {
    rm -f "$TMP"
    rm -rf "$LOCK"
}
trap cleanup EXIT

docker exec "$CONTAINER" pg_dump -U "$USER" -d "$DB" \
    | gzip -9 > "$TMP"
mv "$TMP" "$OUT"
(
    cd "$BACKUP_DIR"
    sha256sum "$(basename "$OUT")" > "$(basename "$OUT").sha256"
)
echo "backup: $OUT ($(du -h "$OUT" | cut -f1))"
echo "sha256: $(cut -d' ' -f1 "$OUT.sha256")"

# Ретеншен: удаляем дампы/чексуммы старше RETENTION_DAYS.
find "$BACKUP_DIR" -name "${DB}-*.sql.gz*" -mtime "+$RETENTION_DAYS" -delete
echo "retention: файлы старше $RETENTION_DAYS дней удалены"
