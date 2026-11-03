#!/usr/bin/env bash
# S-63 в CI: backup→restore smoke (bash-порт scripts/restore-test.ps1).
# Ожидает доступный postgres на localhost:5432 (GH Actions service) и
# миграционную БД с данными (alembic + seed уже прогнаны ранее в job).
# Проверки: sha256 дампа, restore во временную БД, users>=1,
# alembic head = фактурному (arguments); ничего в исходной БД не трогает.
set -euo pipefail

PG_HOST="${PGHOST:-127.0.0.1}"
PG_PORT="${PGPORT:-5432}"
PG_USER="${POSTGRES_USER:-chess}"
PG_PASSWORD="${POSTGRES_PASSWORD:-chess_ci}"
DB="${POSTGRES_DB:-chessclass}"
RESTORE_DB="${DB}_restore"
DUMP="${DUMP_FILE:-/tmp/chessclass-ci.dump}"
EXPECTED_HEAD="${EXPECTED_HEAD:-0028_rag_editor}"

export PGPASSWORD="$PG_PASSWORD"

command -v pg_dump >/dev/null || {
  echo "pg_dump не найден (нужен postgresql-client)" >&2
  exit 1
}

rm -f "$DUMP" "$DUMP.sha256"
pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -Fc "$DB" -f "$DUMP"
sha256sum "$DUMP" | tee "$DUMP.sha256"
( cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "$DUMP").sha256" >/dev/null )
echo "sha256 OK (размер: $(du -h "$DUMP" | cut -f1))"

dropdb -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" --if-exists "$RESTORE_DB" >/dev/null 2>&1 || true
createdb -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" "$RESTORE_DB"
pg_restore -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$RESTORE_DB" \
  --no-owner --no-privileges "$DUMP" >/dev/null 2>&1

users=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$RESTORE_DB" \
  -tAc "SELECT count(*) FROM users")
alembic=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$RESTORE_DB" \
  -tAc "SELECT version_num FROM alembic_version")

echo "restore: users=$users, alembic=$alembic"
if [ "${users:-0}" -lt 1 ]; then
  echo "restore smoke FAILED: users=$users" >&2
  exit 1
fi
if [ "$alembic" != "$EXPECTED_HEAD" ]; then
  echo "restore smoke FAILED: alembic=$alembic (ожидалось $EXPECTED_HEAD)" >&2
  exit 1
fi

dropdb -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" --if-exists "$RESTORE_DB" >/dev/null
echo "restore smoke OK"
