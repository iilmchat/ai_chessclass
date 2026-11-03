# Runbook: staging-контур (S-58, ADR-014)

**Область:** `docker-compose.staging.yml` + `.env.staging` — отдельный staging-стенд
перед prod: собственные порты, volumes и сеть. dev/prod-данные не затрагиваются.
Справочник архитектуры — `Design.md` §2.4/§15.1; prod-эксплуатация — `operations.md`.

## 1. Назначение и порты

Staging — «почти prod» (те же сервисы, edge-nginx, все worker'ы), но с
независимыми именами и портами хоста (ADR-014). Backend-образ — общий
`chessclass/backend:${IMAGE_TAG}`; frontend собирается с `APP_STAGE=staging`
и отдельным тегом `chessclass/frontend:${IMAGE_TAG}-staging`, чтобы бренд
стадии не путался с prod (S-58).

| Сервис | Порт (хост) | Примечание |
|---|---|---|
| `db` (PostgreSQL 17) | **5440** → 5432 | наружу только для отладки/бэкапов |
| `redis` | **6387** → 6379 | AOF, отдельный volume |
| `api` | **127.0.0.1:8032** → 8020 | FastAPI, loopback |
| `web` | **3202** → 80 | SPA-nginx (отладочный вход) |
| `edge` | **8080/8443** | TLS-терминация, HSTS, `/api/` proxy |

Контейнеры `chessclass-staging-*`, volumes `chessclass_staging_*`,
сеть `chessclass-staging-net`. Порты 5440/6387/8032/3202/8080/8443
проверены свободными 2026-11-03 (ADR-014); при занятости — переопределить в
`.env.staging`.

## 2. Предусловия

- Docker Desktop (Compose v2+) запущен; свободные порты из §1.
- TLS-сертификаты для edge (self-signed достаточно):

  ```powershell
  .\scripts\gen-self-signed-cert.ps1 -Force   # deploy/certs/{fullchain.pem,privkey.pem}
  ```

- Окружение staging (секреты — только локально, `.env.staging` в `.gitignore`):

  ```powershell
  Copy-Item .env.staging.example .env.staging
  # заполнить POSTGRES_PASSWORD, JWT_SECRET, SEED_*; LLM/voice/tg — можно оставить пустыми
  ```

## 3. Подъём

```powershell
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d --build
docker compose --env-file .env.staging -f docker-compose.staging.yml ps
```

Миграции выполняет сервис `migrate` до старта API/worker. Seed — вручную
(идемпотентно, только на чистом стенде):

```powershell
docker compose --env-file .env.staging -f docker-compose.staging.yml run --rm migrate
docker compose --env-file .env.staging -f docker-compose.staging.yml run --rm seed
```

## 4. Проверка

```powershell
# API/Web/Edge smoke (healthz, readyz, security headers, SPA)
.\scripts\smoke-prod.ps1 -ApiBase http://127.0.0.1:8032 -WebBase http://localhost:3202 `
  -EdgeBase https://localhost:8443 -SkipCertificateCheck

# readyz: migrationsUpToDate=true, db.revision = db.head = 0028
Invoke-RestMethod http://127.0.0.1:8032/readyz | ConvertTo-Json -Depth 4

# CORS preflight: Origin из allowlist → access-control-allow-origin
curl.exe -k -i -X OPTIONS https://localhost:8443/api/v1/auth/login `
  -H "Origin: https://localhost:8443" `
  -H "Access-Control-Request-Method: POST" `
  -H "Access-Control-Request-Headers: content-type"
# ожидаемо: access-control-allow-origin: https://localhost:8443
# негатив: Origin: http://evil.example → заголовка access-control-allow-origin нет
```

CORS-allowlist задаётся в `.env.staging`: `CORS_ORIGINS=https://localhost:8443,http://localhost:3202`.

LLM/voice smoke (S-59; без ключей — echo-базлайн, с ключами — live,
подробности — `llm-gateway.md` §2.2):

```powershell
docker compose --env-file .env.staging -f docker-compose.staging.yml exec -T api `
  python scripts/llm_smoke.py --mode echo --with-voice --with-pdf `
  --out /srv/reports/llm-smoke-echo.json
# live: --mode live --out /srv/reports/llm-smoke-live.json `
#       --compare /srv/reports/llm-smoke-echo.json
```

## 5. Backup/restore

```powershell
.\scripts\backup.ps1 -Container chessclass-staging-db -BackupDir .\backups\staging
.\scripts\restore-test.ps1 -BackupFile .\backups\staging\chessclass-....dump `
  -Container chessclass-staging-db
```

`restore-test` работает во временной БД `chessclass_restore` и не трогает
staging-БД. Ожидаемо: `sha256 OK`, `users>=1`, `alembic=0028`.

## 6. Остановка и сброс

```powershell
# остановить, данные сохранить (volumes chessclass_staging_* остаются)
docker compose --env-file .env.staging -f docker-compose.staging.yml down

# полный сброс staging-данных (НЕ для prod; пересоздать seed/migrate после)
docker compose --env-file .env.staging -f docker-compose.staging.yml down -v
```

## 7. Отличия окружений

| Параметр | dev | staging | prod |
|---|---|---|---|
| Compose | `docker-compose.dev.yml` | `docker-compose.staging.yml` | `docker-compose.prod.yml` |
| env-file | `.env` | `.env.staging` | `.env` |
| `APP_ENV` | `dev` | `staging` | `prod` |
| pg / redis (хост) | 5438 / 6384 | 5440 / 6387 | не публикуются |
| api / web | 8020 / 3200 | 8032 / 3202 | 8020 / 3200 |
| edge http/https | — | 8080 / 8443 | 80 / 443 |
| образы | `:dev` | backend `IMAGE_TAG` (0.3.0), frontend `0.3.0-staging` | `IMAGE_TAG` (0.3.0) |
| сеть / volumes | `chessclass-net` / `chessclass_*` | `chessclass-staging-net` / `chessclass_staging_*` | `chessclass-prod-net` / `chessclass_prod_*` |
| `WEB_BASE_URL` | — | `https://localhost:8443` | `https://chessclass.example` |

## 8. Известные ограничения

- TLS self-signed → `-SkipCertificateCheck`/`curl -k`; это не валидация реальной
  цепочки сертификатов (LE/продление — `operations.md` §4).
- Живые LLM/voice/LRS/Telegram не подключены — S-59: без ключей/URL работают
  echo/hash-fallback, `LRS_ENABLED=false`, Telegram выключен.
- Cookie `Secure=False` при `APP_ENV=staging` (как dev): refresh-cookie ходит и по
  http://localhost:3202; для https-профиля via edge — только staging, не prod.
- Staging-данные — только в `chessclass_staging_*`; не выполнять на staging
  команды против `chessclass-prod-*`/`chessclass-*` контейнеров (KI-001).
