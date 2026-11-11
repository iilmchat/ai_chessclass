# Release Notes — ChessClass v0.8.0

**Дата:** 2026-11-11 · Спринты **S-90…S-94** (5/5) · релиз
**v0.8.0 Production Readiness**.

Релиз закрывает P0-блокеры DevOps-аудита и переводит проект в состояние,
готовое к пилотному production-запуску в школе. Новых предметных функций нет:
только безопасность, эксплуатация, наблюдаемость и фиксация версии.

## Что нового

### Edge & Auth Hardening (S-90)
- `ProxyHeadersMiddleware` + `PROXY_TRUSTED_HOSTS`: API видит реальный IP
  клиента из `X-Forwarded-For`/`X-Real-IP` доверенного edge/web. Недоверенные
  источники не могут подделать `request.client.host`.
- Lockout переведён с глобального на per-account: 5 неудачных логинов/мин на
  email → `lockout:account:{email}` (10 мин). IP — мягкий лимит 50/мин →
  `lockout:ip:{ip}` (1 мин), поэтому пять неудач одного аккаунта не блокируют
  остальных с того же IP.
- edge nginx: `auth_rl` 10 r/m (burst 9), `api_rl` 60 r/m (burst 30),
  `limit_req_status 429`; smoke `scripts/edge-ratelimit-smoke.ps1` проверяет
  10×200 и 429 на 11-м запросе.
- `JWT_LEGACY_HS256=false` по умолчанию; prod/staging работают на RS256/JWKS
  (`JWT_ALGORITHM=RS256`, `JWT_KID`, PEM-ключи). При legacy/HS256 в
  prod/staging — startup-warning.

### Object-Level Authorization — BOLA (S-91)
- `core/authz.py`: единый слой проверки владения
  (`ensure_can_access_student_data/report/bot/game/submission/pvp_room`).
  admin — всё, teacher — только ученики своих классов, student — свои объекты,
  auditor — только явный scope (fail-closed). Чужой существующий объект → 403,
  отсутствующий → 404.
- Покрыты PDF (генерация/скачивание), `audit/logs`, боты/матчи/реплеи,
  шахматные партии, сдачи, профиль/прогресс/навыки, PvP-комнаты/жалобы,
  флаги и вердикты античита.
- Списки `profile/students`, `admin/audit`, `anticheat/flags|judge`,
  `admin/pvp/complaints` фильтруются по классам/actor/scope.
- Кросс-тенантные тесты `tests/test_authz_cross_tenant.py` на реальных
  RS256-токенах.

### CD, Registry & Observability (S-92)
- GHCR: job `publish` публикует `ghcr.io/iilmchat/chessclass-backend` и
  `chessclass-frontend` с тегами `<sha>` и `<ref>` (для тега — `v0.8.0`).
  Prod-compose тянет образы из GHCR; откат — смена `IMAGE_TAG`.
- Sentry: `SENTRY_DSN`/`SENTRY_ENVIRONMENT`/`SENTRY_TRACES_SAMPLE_RATE` для
  API и worker, `@sentry/react` для frontend (`VITE_SENTRY_DSN`). PII и тела
  запросов выключены, пустой DSN — no-op.
- Логи: Docker json-file 10 МБ × 5 для api/worker/match-workers;
  `deploy/logrotate/chessclass` для файлового запуска.
- Метрики: Prometheus multiprocess mode (`PROMETHEUS_MULTIPROC_DIR`,
  `MultiProcessCollector`) — HTTP RED агрегируются по всем uvicorn-воркерам;
  smoke `scripts/multiprocess-metrics-smoke.ps1` с 2 воркерами.

### SMTP, Offsite Backups & Sandbox (S-93)
- SMTP в prod: `scripts/smtp-smoke.ps1` (локальный sink + verification и
  password-reset), тесты STARTTLS 587 и implicit SSL 465. SMTP обязателен:
  без него email-верификация блокирует регистрацию новых пользователей.
- Offsite-бэкапы: `scripts/backup-offsite.ps1` — `pg_dump -Fc` →
  `openssl enc -aes-256-cbc -pbkdf2` → S3/MinIO/Yandex/VK, JSON-статус
  `size/sha256/duration/s3_path`. `scripts/backup-restore-test.ps1` скачивает,
  расшифровывает и восстанавливает дамп в временный PG 5439, проверяя
  `users`/`alembic_version`. Weekly job в `load.yml` (guard —
  `vars.BACKUP_S3_BUCKET`).
- Алерты: `ChessClassBackupFailed` (>25 ч без успешного бэкапа) и
  `ChessClassBackupRestoreFailed` (`restore_ok == 0`); gauges
  `chessclass_backup_last_success_timestamp_seconds`,
  `chessclass_backup_restore_ok`; всего 10 правил.
- Песочница: `RLIMIT_CPU=1 c` (SIGXCPU/SIGKILL трактуются как
  `TimeoutError`, а не `SandboxCrash`), память 256 МБ, opt-in network
  namespace (`SANDBOX_NETWORK_ISOLATION`), non-root `appuser` uid 1000 в
  backend-образе. Атаки-тесты CPU/network/filesystem — 32 теста sandbox.

## Что требуется от оператора перед запуском

1. **SMTP — обязательно.** Заполнить `SMTP_HOST`, `SMTP_USER`,
   `SMTP_PASSWORD`, `SMTP_FROM` в `.env` (587/STARTTLS или 465/SSL).
   Без рабочего SMTP регистрация блокируется на email-верификации.
2. **Offsite-бэкапы.** Задать `BACKUP_S3_ENDPOINT`, `BACKUP_S3_BUCKET`,
   `BACKUP_S3_ACCESS_KEY`, `BACKUP_S3_SECRET_KEY` и
   `BACKUP_ENCRYPTION_KEY` (32 hex). Без них бэкапы остаются локальными и
   не уходят offsite.
3. **RS256-ключи JWT.** Сгенерировать `.\scripts\gen-jwt-keys.ps1`
   (в `deploy/jwt/`), проверить `JWT_ALGORITHM=RS256`, `JWT_KID` и пути
   `JWT_PRIVATE_KEY_PATH`/`JWT_PUBLIC_KEY_PATH`. `JWT_LEGACY_HS256=false`.
4. **Sentry — опционально.** Задать `SENTRY_DSN` (API/worker) и
   `VITE_SENTRY_DSN` (build-arg frontend). Пустой DSN отключает отправку.
5. **Доверенный прокси.** Проверить `PROXY_TRUSTED_HOSTS` — CIDR edge-сети
   (по умолчанию `172.16.0.0/12,127.0.0.1`). Слишком широкий список
   позволяет подделать IP, слишком узкий — теряет реальный IP клиента.
6. **Прочее.** Проверить `IMAGE_TAG=0.8.0`, домены/CORS, `TELEGRAM_*` для
   алертов, `BACKUP_EXPECTED_ALEMBIC=0035_s83_email_outbox`.

## Числа

- Backend: **328 collected** (325 passed + 3 skipped CSP-группы); ruff/mypy — 0.
- Frontend: Vitest **5 passed**, `tsc`/build — ок.
- UI-e2e: **16 сценариев** Playwright + axe.
- Observability selftest: **21/21 ok** (static + runtime, mTLS, email, gauges).
- SMTP smoke: verification + password-reset доставлены локальным sink.
- Backup restore: `users=15`, `alembic=0035_s83_email_outbox` в temp PG 5439.
- Миграции: **35**, head `0035_s83_email_outbox`; новых миграций в v0.8.0 нет.
- RAG: 13/13; gold: 21/21; doc-lint: 6 checks, 0 failed.
- pip-audit: 0 известных уязвимостей.

## Обновление (prod)

```bash
# 1. Забрать релиз и образы
git fetch --tags && git checkout v0.8.0
IMAGE_TAG=0.8.0 docker compose --env-file .env -f docker-compose.prod.yml pull

# 2. Применить миграции (идемпотентно; новых миграций нет)
docker compose --env-file .env -f docker-compose.prod.yml run --rm migrate

# 3. Перезапустить стек
IMAGE_TAG=0.8.0 docker compose --env-file .env -f docker-compose.prod.yml up -d

# 4. Проверить готовность
curl -fsS https://<host>/healthz
curl -fsS https://<host>/api/v1/readyz
```

- Образы: `ghcr.io/iilmchat/chessclass-backend:v0.8.0`,
  `ghcr.io/iilmchat/chessclass-frontend:v0.8.0` (плюс тег `<sha>` для
  точного отката).
- Перед обновлением — свежий бэкап (`.\scripts\backup.ps1` или
  `backup-offsite.ps1`) и проверка `.\scripts\check-cert-expiry.ps1`.
- **Windows:** для `backup-offsite.ps1` / `backup-restore-test.ps1` передавать
  абсолютный `-BackupDir` (например,
  `-BackupDir C:\backups\chessclass`). Относительный путь Docker трактует как
  named volume, и шифрование/restore падает; исправление — в v0.8.1.
- После обновления — smoke: `.\scripts\smoke-prod.ps1 -EdgeBase https://<host>`,
  `.\scripts\smtp-smoke.ps1`, `.\scripts\backup-restore-test.ps1`.
- **Откат:** выставить `IMAGE_TAG` предыдущего релиза (`0.7.1`) и повторить
  `pull`/`up -d`; схема БД совместима (миграций не добавлялось).

## Известные ограничения

- **Live LRS/TTS не проверены вживую** — нет боевых ключей LRS/ElevenLabs;
  проверены mock-контракты и fallback-поведение (S-81 остаётся отложенным).
- **GPU-туннель не подключён** — нет физической станции RTX 3060 + LM Studio
  (S-84 отложен); локальный LLM-фолбэк работает через конфигурацию, но
  end-to-end на железе не принимался.
- **Network namespace в песочнице — opt-in.** `unshare -n` требует
  root/CAP_SYS_ADMIN, а worker работает non-root; в prod режим выключен.
  Альтернатива — отдельный контейнер `network_mode: none` (не развёрнут).
- **Боевой SMTP-провайдер не проверен** — smoke идёт в локальный sink;
  SPF/DKIM/DMARC, bounce и квоты проверяются на стенде оператора.
- **Боевой S3-провайдер не проверен** — загрузка/restore проверены на
  S3-совместимом S3Mock; IAM, lifecycle и регион — на стенде.
- **Полный prod-деплой не выполнялся** в рамках спринта: проверены
  compose-конфигурация, Docker-контуры и self-tests, но не боевые секреты.

## Ссылки

- [CHANGELOG](CHANGELOG.md) · [S-90](sprint-reports/S-90-2026-11-11.md) ·
  [S-91](sprint-reports/S-91-2026-11-11.md) ·
  [S-92](sprint-reports/S-92-2026-11-11.md) ·
  [S-93](sprint-reports/S-93-2026-11-11.md) ·
  [S-94](sprint-reports/S-94-2026-11-11.md)
- Runbooks: [operations](runbooks/operations.md) (§11–§18),
  [staging](runbooks/staging.md)
