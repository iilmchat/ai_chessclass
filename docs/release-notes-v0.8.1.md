# Release Notes — ChessClass v0.8.1 (patch)

**Дата:** 2026-11-11 · Патч к **v0.8.0** · Новых функций нет.

## Исправлено

- **Абсолютный `-BackupDir` в backup-скриптах.** На Windows
  `docker run -v "backups:/backup"` трактовал относительный путь как named
  volume, поэтому `backup-offsite.ps1` и `backup-restore-test.ps1` падали
  (пустой каталог внутри контейнера). Теперь `-BackupDir` и `-BackupFile`
  резолвятся в абсолютный путь до `docker -v`; при отсутствии каталог
  создаётся. Дефект выявлен в [S-94 §3](sprint-reports/S-94-2026-11-11.md).
- `backup-offsite.ps1 -DryRun` выводит итоговый `backup_dir`, `status_file`
  и `docker_mount` без выполнения; smoke
  `scripts/backup-relative-dir-smoke.ps1` проверяет относительный путь.
- Runbook [operations §17](runbooks/operations.md) дополнен примечанием о
  путях и исправлении.

## Проверка

- `scripts/backup-relative-dir-smoke.ps1` → абсолютный `docker_mount`.
- `backup-offsite.ps1 -BackupDir .\backups-v081-test` → `status=ok`;
  `backup-restore-test.ps1` с относительным `-BackupDir` →
  `users=15`, `alembic=0035_s83_email_outbox`.
- `ci.ps1`, `e2e.ps1 test`, `smtp-smoke.ps1`,
  `observability-selftest.ps1 -Stack`, pip-audit, doc-lint — зелёные.

## Обновление

```bash
git fetch --tags && git checkout v0.8.1
# GHCR публикует тег с префиксом v (git tag): v0.8.1
IMAGE_TAG=v0.8.1 docker compose --env-file .env -f docker-compose.prod.yml pull
docker compose --env-file .env -f docker-compose.prod.yml run --rm migrate
IMAGE_TAG=v0.8.1 docker compose --env-file .env -f docker-compose.prod.yml up -d
```

- Образы: `ghcr.io/iilmchat/chessclass-backend:v0.8.1`,
  `ghcr.io/iilmchat/chessclass-frontend:v0.8.1`. В `IMAGE_TAG` для
  GHCR указывайте `v0.8.1` (тег релиза), в `.env.example` — базовую
  версию `0.8.1`.
- Миграций нет; схема БД совместима с v0.8.0.
- Откат — `IMAGE_TAG=0.8.0` и повторный `pull`/`up -d`.

## Известные ограничения

Без изменений относительно v0.8.0: live LRS/TTS и GPU-туннель не проверены
вживую, network namespace в песочнице — opt-in, боевые SMTP/S3-провайдеры
проверяются на стенде оператора.
