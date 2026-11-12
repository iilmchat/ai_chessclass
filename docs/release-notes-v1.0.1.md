# Release Notes — ChessClass v1.0.1 «Production Ready Fix»

**Статус:** ✅ Выпущен · **Дата:** 2026-11-12 · **База:** v1.0.0 ·
**Тип:** patch (hotfix деплоя и безопасности) · **Тег:** `v1.0.1` ·
**Миграции:** `0036_s98_legal_hold` (36, без изменений)

> Патч закрывает два P0-блокера, из-за которых первый production-деплой
> v1.0.0 либо падал на `docker compose pull`, либо поднимался с молча
> отключёнными SMTP/бэкапами. Дополнительно усилены безопасность web-порта
> и стабильность Alertmanager. Продуктовые API/миграции не менялись.

## Исправлено

### P0-1. Тег GHCR и `IMAGE_TAG` теперь совпадают

- Workflow `publish` использует `docker/metadata-action`:
  тег `v1.0.1` публикуется в GHCR как **`1.0.1`** (semver без префикса
  `v`), плюс неизменяемый `:<sha>` и `:main` для main-сборок.
- `docker-compose.prod.yml`, `docker-compose.staging.yml`,
  `.env.prod.example`, `.env.staging.example` используют
  `IMAGE_TAG=1.0.1`.
- `docker compose pull` работает из коробки, обход `IMAGE_TAG=v1.0.1`
  больше не нужен.

### P0-2. `env_file` доносит `.env.prod` до контейнеров

- В `.env.prod.example` добавлен `ENV_FILE=.env.prod`
  (в staging — `ENV_FILE=.env.staging`). Сервисы читают тот же файл, что и
  compose, поэтому `SMTP_*`, `BACKUP_S3_*`, `LRS_*`, `TELEGRAM_*`,
  `PROXY_TRUSTED_HOSTS` попадают в контейнеры при запуске с
  `--env-file .env.prod`.
- `docker-compose.prod.yml`: директива `env_file: ${ENV_FILE:-.env}`
  применяется к `migrate`, `api`, `worker`, `worker-match-*` и `seed`.

### P1-1. Web доступен только через edge

- В `docker-compose.prod.yml` порт web изменён с `0.0.0.0:3200` на
  `127.0.0.1:${WEB_PORT:-3200}`. Наружу смотрят только edge-nginx
  (80/443); web недоступен напрямую из интернета.

### P1-6. Alertmanager не падает без Telegram

- `alertmanager-render.sh` больше не требует `TELEGRAM_BOT_TOKEN` и
  `TELEGRAM_ALERT_CHAT_ID`: при пустых значениях Telegram-блоки удаляются,
  а `route.receiver` переключается на `"null"`. Контейнер стартует без
  CrashLoopBackOff; алерты не уходят в Telegram, пока ключи не заданы.
- Email-receiver по-прежнему включается только при заданных `SMTP_HOST` и
  `ALERT_EMAIL_TO`.
- `observability-selftest.ps1`: добавлена проверка рендера без Telegram
  (`receiver: "null"`, `amtool check-config`).

### P2-1. Gitleaks: ложные срабатывания

- Добавлен `.gitleaksignore` с комментариями: лог-строка о legacy HS256
  (имя настройки, не секрет) и фиктивный selftest-токен Alertmanager.
  Исторические находки больше не шумят при локальном `gitleaks detect`.

## Документация

- `docs/runbooks/production-deployment-v1.0.1.md` — обновлённый runbook:
  `IMAGE_TAG=1.0.1`, `.env.prod` + `ENV_FILE`, loopback web, опциональный
  Telegram, откат на `1.0.0`.
- `docs/runbooks/production-readiness-checklist.md` — чек-лист v1.0.1.
- `docs/sprint-reports/infra-audit-v1.0.0-2026-11-12.md` — аудит, на
  котором основан патч.
- `docs/sprint-reports/S-102-fix-v1.0.1-2026-11-12.md` — отчёт hotfix.

## Обновление (prod)

1. Получить тег и образы:

   ```bash
   git fetch --tags
   git checkout v1.0.1
   docker pull ghcr.io/iilmchat/chessclass-backend:1.0.1
   docker pull ghcr.io/iilmchat/chessclass-frontend:1.0.1
   ```

2. Обновить `.env.prod`:

   ```dotenv
   IMAGE_TAG=1.0.1
   ENV_FILE=.env.prod
   ```

3. Применить миграции (идемпотентно) и перезапустить:

   ```bash
   docker compose --env-file .env.prod -f docker-compose.prod.yml pull
   docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm migrate
   docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
   ```

4. Проверить:

   ```bash
   curl -fsS http://127.0.0.1:8020/healthz
   curl -fsS http://127.0.0.1:8020/readyz
   ss -ltnp | grep -E ':(80|443|3200)\b'   # 3200 — только 127.0.0.1
   ```

5. **Откат:** `IMAGE_TAG=1.0.0` в `.env.prod`, затем `pull` и `up -d`.
   Схема БД не менялась, миграции forward-only.

## Проверки

- Backend: **347** собранных теста (344 passed + 3 skipped), ruff/mypy — 0.
- Frontend: **7 passed** (Vitest), `tsc`/`vite build` — OK.
- UI-e2e: **17 passed** (Playwright).
- `ci.ps1`, `e2e.ps1 test`, `observability-selftest.ps1` (static),
  `pip-audit`, doc-lint, аудит алфавитов, `git diff --check` — зелёные.
- GHCR: `ghcr.io/iilmchat/chessclass-backend:1.0.1` и
  `...-frontend:1.0.1` (semver без `v`), `docker pull` — OK.

## Известные ограничения

- **S-95 (Live LRS/TTS)** остаётся отложенным до v1.1.0 (нет боевых ключей
  LRS/ElevenLabs); контракты и fallback покрыты тестами.
- Остальные P1/P2 аудита (лимиты CPU/RAM, пул БД, авто-renew TLS,
  Linux-offsite-бэкап, UFW/fail2ban, DNS-runbook) — в бэклоге v1.1.0.
