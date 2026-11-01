# Runbook: эксплуатация ChessClass (S-38)

**Область:** prod-стек (`docker-compose.prod.yml`), edge-TLS, бэкапы,
восстановление, секреты, базовые инциденты. LLM-шлюз — отдельный
`docs/runbooks/llm-gateway.md`.

## 1. Стек и порты

| Сервис | Порт (prod) | Примечание |
|---|---|---|
| `edge` | 80 → 443 | TLS-терминация, HSTS, security headers |
| `web` | 3200 (loopback/отладка) | SPA nginx, `/api/` proxy |
| `api` | 8020 (loopback) | FastAPI, 4 воркера |
| `db` | внутри сети 5432 | наружу не публикуется |
| `redis` | внутри сети 6379 | наружу не публикуется |
| `worker` + 4 `worker-match-*` | — | analyze/pdf + per-queue матчи |

Проверка:

```powershell
.\scripts\smoke-prod.ps1 -ApiBase http://127.0.0.1:8020 `
  -WebBase http://localhost:3200 `
  -EdgeBase https://localhost -SkipCertificateCheck
```

`edge` отдаёт `Strict-Transport-Security`, `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`; HTTP
редиректит на HTTPS (кроме ACME).

## 2. Бэкапы

### 2.1. Windows (Task Scheduler)

```powershell
# разово
.\scripts\backup.ps1 -Container chessclass-prod-db -BackupDir D:\backups\chessclass

# nightly 03:00 (от администратора)
.\scripts\install-backup-task.ps1 -BackupDir D:\backups\chessclass
```

### 2.2. Linux (cron)

```bash
cp deploy/cron/chessclass-backup /etc/cron.d/
chmod 0644 /etc/cron.d/chessclass-backup
# BACKUP_DIR=/var/backups/chessclass, retention 14 дней
```

### 2.3. Ручной запуск (Linux)

```bash
cd /opt/chessclass
BACKUP_DIR=/var/backups/chessclass BACKUP_RETENTION_DAYS=14 \
  bash backend/scripts/backup.sh
```

Формат: `chessclass-YYYYMMDDTHHMMSSZ.sql.gz` + `.sha256`;
retention 14 дней; lock-файл против параллельных запусков. Копии
рекомендуется увозить на отдельный диск/в object storage (не в git).

## 3. Проверка восстановления

Безопасно, во временную БД (prod-БД не трогается):

```powershell
.\scripts\restore-test.ps1 -BackupFile D:\backups\chessclass\chessclass-....dump `
  -Container chessclass-prod-db
```

Скрипт проверяет sha256, создаёт `chessclass_restore`, делает
`pg_restore`/`psql`, проверяет `users` и `alembic_version`, затем удаляет
временную БД. Ожидаемо: `[restore] OK: users=N alembic=0014_reports`.

### 3.1. Полное восстановление prod (простой)

1. Остановить API/worker/edge (БД не принимает запросы):
   `docker compose -f docker-compose.prod.yml stop edge api worker worker-match-random worker-match-greedy worker-match-minimax worker-match-sf`
2. Сделать текущий аварийный дамп, если БД ещё доступна.
3. Восстановить в **новую** БД `chessclass_restore`, проверить (см. §3).
4. Переключить `POSTGRES_DB`/DATABASE_URL на восстановленную БД или
   переименовать БД; выполнить `alembic upgrade head`.
5. Запустить `migrate`, затем API/worker/edge; проверить `readyz` и smoke.
6. Сохранить старую БД/volume до подтверждения, затем удалить.

## 4. TLS

### 4.1. Self-signed (стенд/локально)

```powershell
.\scripts\gen-self-signed-cert.ps1 -Force
# сертификаты в deploy/certs/{fullchain.pem,privkey.pem}
```

### 4.2. Let's Encrypt / production

```bash
certbot certonly --webroot -w /var/www/certbot -d chessclass.example
cp /etc/letsencrypt/live/chessclass.example/fullchain.pem deploy/certs/
cp /etc/letsencrypt/live/chessclass.example/privkey.pem deploy/certs/
docker compose -f docker-compose.prod.yml restart edge
```

Продление: `certbot renew` + restart edge (cron/systemd timer). Проверка:
`curl -kI https://chessclass.example/` → HSTS; `smoke-prod.ps1 -EdgeBase ...`.
Приватные ключи не коммитить; `deploy/certs/.gitignore` уже исключает `*.pem`.

## 5. Секреты и ротация

- `.env`/`.env.prod` — только на сервере, не в git/чатах/логах.
- Ротация `JWT_SECRET` инвалидирует access-токены; refresh-cookie — при
  следующем логине. Плановая ротация — с окном обслуживания.
- Ротация `POSTGRES_PASSWORD`: обновить `.env`, `ALTER USER`, перезапуск
  api/worker/migrate.
- Ротация `LLM_API_KEY` — см. `llm-gateway.md` §4.
- Seed-пароли менять до первого prod-запуска; после — через админку/смену
  пароля, не пересидировать.

## 6. Инциденты

| Симптом | Действие |
|---|---|
| `readyz` не ready | проверить `docker compose ps`, логи api/db; миграции/БД |
| API 5xx | логи api; проверить БД/Redis, диск, LLM-провайдера |
| Матчи висят | проверить `worker-match-*` и `GET /admin/matches/metrics`; очередь/лимиты |
| LLM деградировал | health `/admin/llm/health`; echo/fallback — штатно |
| Диск заполнен | бэкапы/логи/PDF; retention, очистка старых отчётов |
| Сертификат истёк | продлить/положить новый, `restart edge`, smoke |
| Утечка ключа | отозвать ключ, ротация, аудит `llm_calls`/логов |

Логи: `docker compose -f docker-compose.prod.yml logs --tail=200 <service>`.
Не удалять чужие контейнеры/volumes (KI-001); работать только с
`chessclass-*`/`chessclass-prod-*`.

## 7. Плановые проверки

- Ежедневно: backup task + `restore-test` раз в неделю.
- Еженедельно: `smoke-prod.ps1`, `GET /admin/matches/metrics`,
  `GET /admin/llm/health`.
- Перед релизом: backend CI (ruff/mypy/pytest), frontend build, Playwright
  e2e (`.\scripts\e2e.ps1 test`), prod smoke.
