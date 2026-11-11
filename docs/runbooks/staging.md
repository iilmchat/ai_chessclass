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

- **Live LRS OAuth2 (S-79):** для внешнего провайдера задайте
  `LRS_ENABLED=true`, `LRS_ENDPOINT=https://<lrs>/xapi`,
  `LRS_OAUTH_TOKEN_URL=https://<idp>/oauth/token`,
  `LRS_OAUTH_CLIENT_ID`, `LRS_OAUTH_CLIENT_SECRET` (и scope при необходимости).
  Токен кешируется в Redis (`lrs:oauth:token`), при 401 обновляется и xAPI
  PUT повторяется один раз. Basic (`LRS_KEY`/`LRS_SECRET`) — fallback, если
  OAuth-переменные не заданы.

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

# readyz: migrationsUpToDate=true, db.revision = db.head = 0035
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

**CSP (S-61).** Web-nginx излучает CSP; в staging стоит `CSP_MODE=report-only`
(в `.env.staging.example`) — браузер пишет нарушения в консоль, не блокируя.
Аудит: в e2e/Playwright слушать `console`-события `csp-violation` — пусто
→ перевести `CSP_MODE=report-only` → удалить (enforce, как в prod).

**Egress (S-61).** Все исходящие звонки (LLM/voice/Telegram/LRS) проходят
allowlist `core/egress.py`: базовые URL провайдеров разрешены сами; прочие
хосты — в `ALLOWED_EGRESS_HOSTS` (комма/JSON, `host` или `*.host`).
Проверка:

```powershell
docker compose --env-file .env.staging -f docker-compose.staging.yml exec -T api `
  python -c "from core.egress import ensure_egress_allowed as f; f('https://api.example.com/x')"
# ожидаемо 502 egress_blocked, если host не в списке
```

LLM/voice smoke (S-59; без ключей — echo-базлайн, с ключами — live,
подробности — `llm-gateway.md` §2.2):

```powershell
docker compose --env-file .env.staging -f docker-compose.staging.yml exec -T api `
  python scripts/llm_smoke.py --mode echo --with-voice --with-pdf `
  --out /srv/reports/llm-smoke-echo.json
# live: --mode live --out /srv/reports/llm-smoke-live.json `
#       --compare /srv/reports/llm-smoke-echo.json
```

## 4.1. Staging Acceptance (v0.8.1)

Операционная приёмка v0.8.1 на стенде с боевыми SMTP/S3. Скрипт **не**
заменяет проверку провайдера: он проверяет API, JWKS, backup-метрику и
observability, а доставку письма подтверждает оператор.

**Перед запуском** заполнить `.env.staging` (все секреты — только локально):

```dotenv
SMTP_HOST=CHANGE_ME
SMTP_PORT=587
SMTP_USER=CHANGE_ME
SMTP_PASSWORD=CHANGE_ME
SMTP_FROM=noreply@example.com
SMTP_STARTTLS=true
SMTP_SSL=false

BACKUP_S3_ENDPOINT=            # пусто для AWS; Yandex/VK/MinIO — URL
BACKUP_S3_BUCKET=CHANGE_ME
BACKUP_S3_PREFIX=postgres-staging
BACKUP_S3_ACCESS_KEY=CHANGE_ME
BACKUP_S3_SECRET_KEY=CHANGE_ME
BACKUP_ENCRYPTION_KEY=         # ровно 32 hex-символа

JWT_ALGORITHM=RS256
JWT_LEGACY_HS256=false
JWT_KID=staging-2026-11
PROXY_TRUSTED_HOSTS=172.16.0.0/12,127.0.0.1
SENTRY_DSN=                    # пусто = Sentry выключен
```

RS256-ключи: `.\scripts\gen-jwt-keys.ps1` (пути
`JWT_PRIVATE_KEY_PATH`/`JWT_PUBLIC_KEY_PATH`). После изменения env:
`docker compose --env-file .env.staging -f docker-compose.staging.yml up -d`.

**Запуск приёмки:**

```powershell
.\scripts\staging-acceptance.ps1 `
  -BaseUrl https://localhost:8443/api/v1 `
  -AdminEmail admin@example.com `
  -AdminPassword '<боевой-пароль>' `
  -TestStudentEmail accept-2026-11-11@example.com
```

`-TestStudentEmail` — одноразовый адрес с доступом к ящику (лучше
plus-адрес). `-AdminPassword` не коммитить и не писать в общий журнал; при
повторе используйте новый тестовый email. `BaseUrl` можно передать как
origin (`https://host`) или как `.../api/v1`.

Скрипт выводит таблицу `Check | Result | Details` и коды:
`0` — всё ok, `1` — warning, `2` — critical. Пароли/токены не логируются.

| Проверка | Что означает | Действие при провале |
|---|---|---|
| `healthz` | API видит PostgreSQL и Redis | `docker compose ps`, логи `api/db/redis`; поднять стек |
| `readyz` | миграции применены (`migrationsUpToDate=true`) | `run --rm migrate`; сверить revision/head |
| `admin_login` | admin существует, пароль верный, нет lockout | проверить seed/пароль; снять lockout в Redis |
| `jwks` | RS256/JWKS непустой, есть `kid` | проверить `JWT_*` и PEM-ключи; перезапустить api |
| `student_register` | регистрация ученика | 409 — сменить тестовый email; 429 — подождать rate-limit |
| `email_outbox` | строка outbox в статусе `sent` (если есть) | проверить SMTP/провайдера; verify-письмо синхронное |
| `backup_metric` | `chessclass_backup_last_success_timestamp_seconds > 0` | выполнить offsite-бэкап (ниже) и повторить |
| `observability` | summary/alerts без critical | разобрать `/admin/observability/alerts`, §10 operations |

`email_outbox` по умолчанию `SKIP`, если строки для тестового адреса нет:
verify-письмо отправляется синхронно, а не через outbox. Для строгой
проверки добавьте `-RequireEmailOutbox` (тогда отсутствие строки — `FAIL`);
для consent-писем outbox проверяется SQL ниже.

## 4.2. Боевые SMTP/S3 (v0.8.1)

### SMTP

1. Заполнить `SMTP_*` в `.env.staging`; для 465 — `SMTP_SSL=true`,
   `SMTP_STARTTLS=false`; для 587 — наоборот.
2. Запустить `.\scripts\smtp-smoke.ps1` (локальный sink, проверка
   транспорта) и `staging-acceptance.ps1` (регистрация).
3. Проверить **реальный ящик** `TestStudentEmail`: письмо
   «Подтвердите email — ChessClass», папка «Спам», заголовки `From`,
   `Return-Path`, SPF/DKIM/DMARC у провайдера.
4. Для consent/outbox:

   ```powershell
   docker compose --env-file .env.staging -f docker-compose.staging.yml exec -T db `
     psql -U chess -d chessclass -c `
     "SELECT recipient, kind, status, attempts, last_error, created_at FROM email_outbox ORDER BY created_at DESC LIMIT 10;"
   ```

   `sent` — доставлено; `pending` — worker ещё не обработал; `failed` с
   `attempts >= EMAIL_OUTBOX_MAX_ATTEMPTS` — parked, разобрать
   `last_error` и вернуть строку точечно (operations §18).
5. При 5xx: 535 — логин/пароль, 550 — политика получателя, 421/451 —
   временный отказ (retry сам). Bounce приходит на `SMTP_FROM`/return-path.

### S3

1. Заполнить `BACKUP_S3_*` и `BACKUP_ENCRYPTION_KEY` (32 hex).
2. Запустить offsite-бэкап с **абсолютным или относительным** `-BackupDir`
   (v0.8.1 резолвит путь сам):

   ```powershell
   .\scripts\backup-offsite.ps1 -Container chessclass-staging-db `
     -BackupDir .\backups\staging
   ```

   Ожидаемо: JSON `status=ok`, `size_bytes`, `sha256`, `s3_path`.
3. Проверить объект в консоли провайдера или CLI:

   ```powershell
   aws --endpoint-url $env:BACKUP_S3_ENDPOINT s3 ls `
     "s3://$env:BACKUP_S3_BUCKET/postgres-staging/"
   ```

   Сверить размер/дату; скачать объект и проверить sha256 при необходимости.
4. Restore-test:

   ```powershell
   .\scripts\backup-restore-test.ps1 -BackupDir .\backups\staging
   ```

   Ожидаемо: `users=15`, `alembic=0035_s83_email_outbox` (или актуальный
   head), временный PG 5439 удалён.
5. Lifecycle: на bucket — `Expiration: 30` дней (S3 Lifecycle / правило
   провайдера); локально `BACKUP_DIR` — 14 дней. Ключи/S3-секреты не
   коммитить и не печатать в логи. Алерты — `ChessClassBackupFailed`
   (>25 ч) и `ChessClassBackupRestoreFailed`.

## 5. Backup/restore

```powershell
.\scripts\backup.ps1 -Container chessclass-staging-db -BackupDir .\backups\staging
.\scripts\restore-test.ps1 -BackupFile .\backups\staging\chessclass-....dump `
  -Container chessclass-staging-db
```

`restore-test` работает во временной БД `chessclass_restore` и не трогает
staging-БД. Ожидаемо: `sha256 OK`, `users>=1`,
`alembic=0035_s83_email_outbox` (актуальный head).

Offsite-бэкап и restore-test с S3 — §4.2; оба скрипта принимают
относительный `-BackupDir` (v0.8.1 резолвит его в абсолютный путь).

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
| образы | `:dev` | backend `IMAGE_TAG` (0.8.1), frontend `0.8.1-staging` | `IMAGE_TAG` (0.8.1) |
| сеть / volumes | `chessclass-net` / `chessclass_*` | `chessclass-staging-net` / `chessclass_staging_*` | `chessclass-prod-net` / `chessclass_prod_*` |
| `WEB_BASE_URL` | — | `https://localhost:8443` | `https://chessclass.example` |
| `CSP_MODE` (S-61) | default `enforce` (задавать не нужно) | `report-only` (до аудита) | default `enforce` |
| `ALLOWED_EGRESS_HOSTS` (S-61) | доп. хосты сверх базовых URL | то же | то же |

## 8. Известные ограничения

- TLS self-signed → `-SkipCertificateCheck`/`curl -k`; это не валидация реальной
  цепочки сертификатов (LE/продление — `operations.md` §4).
- LLM live проверен 2026-11-03 (RouterAI, 4/4 `status=ok`, cost 1.3629 ₽; см.
  отчёт S-59); без ключа — echo/hash-fallback (`llm_smoke.py --mode echo`).
- Voice: ElevenLabs geo-block из РФ (`geo-restriction.elevenlabs.io`) — TTS
  недоступен, voice остаётся graceful off; альтернативный TTS — backlog
  (`TODO_V0.4.md`).
- LRS/Telegram — S-67/S-68: без endpoint/токена выключены
  (`LRS_ENABLED=false`, `TELEGRAM_BOT_TOKEN` пуст).
- Cookie `Secure=False` при `APP_ENV=staging` (как dev): refresh-cookie ходит и по
  http://localhost:3202; для https-профиля via edge — только staging, не prod.
- Staging-данные — только в `chessclass_staging_*`; не выполнять на staging
  команды против `chessclass-prod-*`/`chessclass-*` контейнеров (KI-001).
