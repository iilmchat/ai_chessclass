# Release Notes — ChessClass v0.9.0

**Дата:** 2026-11-12 · Минорный релиз к **v0.8.1** · Цикл
«Live, Isolation & Retention» (S-95…S-99).

## Что нового

### Sandbox Network Isolation (S-97)

- Песочница Python-заданий изолирована по сети **по умолчанию**:
  `bwrap --unshare-net` под uid 1000, без `--privileged` и
  `CAP_SYS_ADMIN`. Сеть контейнера (Redis, БД, интернет) из кода задания
  недоступна — `socket.connect` завершается отказом.
- `deploy/seccomp-sandbox.json` — Docker default seccomp + namespace/mount
  syscalls, необходимые bubblewrap; подключён к `api`, `worker` и
  `worker-match-*` во всех compose-файлах.
- `SANDBOX_NETWORK_ISOLATION=true`, `SANDBOX_NETWORK_BACKEND=auto`
  (`auto|bwrap|unshare|none`). Если bwrap недоступен (ядро/seccomp),
  executor откатывается на `unshare` или plain-режим с warning, а в
  результате выставляет `network_isolation_enforced=false` и
  `network_backend` — это видно в UI/аудите.
- Runbook [operations §19](runbooks/operations.md) — диагностика bwrap,
  проверка изоляции и fallback.

### Retention & Legal Hold (S-98)

- **Retention `email_outbox`:** тело писем `sent`/`failed` заменяется на
  `[deleted]` через 30 дней (`EMAIL_OUTBOX_BODY_RETENTION_DAYS`), метаданные
  удаляются через 90 дней (`EMAIL_OUTBOX_RETENTION_DAYS`); архив пишется
  gzip-JSONL **без body**. `pending` не затрагивается.
- **Legal Hold:** таблица `legal_holds` (миграция `0036_s98_legal_hold`) и
  admin API `POST/DELETE/GET /admin/legal-holds`; retention пропускает
  субъекта под активным hold и пишет `retention.skipped_legal_hold` в
  `audit_logs`.
- **DSAR erase:** `POST /admin/users/{id}/erase` анонимизирует пользователя
  и профиль, удаляет outbox/tokens/sessions/links/review/pvp и стирает
  код/партии; при активном hold — `409 legal_hold_active`; audit
  `user.erased`.
- Метрики: `chessclass_legal_holds_active_total`,
  `chessclass_email_outbox_body_pending_scrub_total`,
  `chessclass_retention_last_success_timestamp_seconds`; алерты
  `ChessClassLegalHoldActive` (info) и `ChessClassRetentionFailed`.
- Политика конфиденциальности §9 и runbook [operations §20](runbooks/operations.md)
  описывают hold/DSAR.

### GPU Tunnel — подготовка (S-96)

- Внешняя GPU-станция (Windows, RTX 3060 12 GB, LM Studio + Qwen2.5-7B)
  подключается reverse SSH-туннелем; сервер видит её как
  `http://172.18.0.1:8035/v1`.
- Новый `LLM_LOCAL_MODEL` задаёт id модели LM Studio (иначе провайдер
  отправлял облачный slug и получал 404). Цепочка fallback: cloud → local
  → echo, breaker local после 5 ошибок.
- `scripts/test-gpu-tunnel.ps1` проверяет `models`/`chat`, latency и
  tokens-per-second; `scripts/wg-gpu-tunnel.ps1` — Windows-цикл туннеля.
- Инструкция станции — [llm-gateway runbook §6](runbooks/llm-gateway.md).
  **Live-запрос через физическую станцию выполняет оператор** (см.
  «Известные ограничения»).

## Отложено

### Live LRS/TTS (S-95, ранее S-81)

Спринт **не входит** в v0.9.0: нет боевых ключей LRS/ElevenLabs и доступа
к провайдерам. Без них нельзя проверить OAuth2/refresh, квоты, rate-limit,
стоимость TTS и фактическую доставку писем. Код и контракты готовы
(токен в Redis, refresh при 401, fallback TTS, SMTP-транспорт); приёмка
остаётся за оператором стенда после выдачи ключей. План — `TODO_V0.9.md`
S-95 (⏸️).

## Обновление (prod)

```bash
git fetch --tags && git checkout v0.9.0

# GHCR публикует тег с префиксом v (git tag): v0.9.0
IMAGE_TAG=v0.9.0 docker compose --env-file .env -f docker-compose.prod.yml pull

# Миграции: 0036_s98_legal_hold (36-я)
docker compose --env-file .env -f docker-compose.prod.yml run --rm migrate

IMAGE_TAG=v0.9.0 docker compose --env-file .env -f docker-compose.prod.yml up -d
```

1. **Перед обновлением** сверьте `.env`: `IMAGE_TAG=0.9.0`,
   `SANDBOX_NETWORK_ISOLATION=true`, `SANDBOX_NETWORK_BACKEND=auto`,
   `EMAIL_OUTBOX_BODY_RETENTION_DAYS=30`, `EMAIL_OUTBOX_RETENTION_DAYS=90`;
   для GPU — `LLM_LOCAL_FALLBACK`, `LLM_LOCAL_BASE_URL`,
   `LLM_LOCAL_MODEL`, `LLM_LOCAL_API_KEY`.
2. **seccomp:** файл `deploy/seccomp-sandbox.json` должен существовать на
   хосте — compose ссылается на него для `api`/`worker`. После старта
   проверьте в результате запуска задания `network_backend=bwrap` и
   `network_isolation_enforced=true`; иначе смотрите runbook §19.
3. **Миграция `0036_s98_legal_hold`** создаёт `legal_holds`; откат схемы не
   автоматический — при откате на v0.8.1 таблица останется (не мешает).
4. **Проверка:** `curl http://localhost:8020/healthz` → `status=ok`,
   `/readyz` → `migrationsUpToDate=true`; `scripts/smoke-prod.ps1`.
5. **Откат:** `IMAGE_TAG=0.8.1 docker compose … pull && … up -d`.

Образы: `ghcr.io/iilmchat/chessclass-backend:v0.9.0`,
`ghcr.io/iilmchat/chessclass-frontend:v0.9.0`. В `.env.example` —
базовая версия `0.9.0`, в `IMAGE_TAG` для GHCR — тег релиза `v0.9.0`.

## Проверка релиза

- `ci.ps1` — backend ruff/mypy/pytest; `e2e.ps1 test` — Playwright;
  `smtp-smoke.ps1`, `observability-selftest.ps1 -Stack`, `pip-audit`,
  `doc-lint` — зелёные (факты — в
  [отчёте S-99](sprint-reports/S-99-2026-11-12.md)).
- `doc-lint`: версии 0.9.0 согласованы, прогресс активного плана `4/5`,
  release notes v0.9.0 на месте.

## Известные ограничения

- **Live LRS/TTS** (S-95) — отложен, нет боевых ключей.
- **GPU live** — серверная часть и скрипты готовы, фактический запрос через
  станцию выполняет оператор (`test-gpu-tunnel.ps1`).
- **Staging-приёмка v0.8.1** с боевыми SMTP/S3/RS256-ключами остаётся
  операционной задачей ([чек-лист](sprint-reports/staging-acceptance-2026-11-11.md)).
- **bwrap на старых ядрах:** при недоступности namespace-операций
  включается fallback с warning; для полной изоляции нужен
  `deploy/seccomp-sandbox.json` и современное ядро хоста.
