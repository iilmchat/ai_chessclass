# Release Notes — ChessClass v0.7.1

**Дата:** 2026-11-10 · Спринты **S-86…S-89** (4/4) · релиз
**v0.7.1 Tech Debt Cleanup**.

Технический патч поверх v0.7.0: надёжность email-очереди, hardening
observability, ротация сертификатов и retention-ops. Отдельно зафиксировано
снятие юридического блокера: все 16 вопросов `docs/legal-review-v0.7.md`
закрыты юристом 2026-11-08 на уровне бизнес-договорённостей, без изменений
в коде.

## Что нового

### Email Outbox Hardening (S-86)
- `deliver_pending` использует `SELECT … FOR UPDATE SKIP LOCKED`: параллельные
  cron-воркеры не отправляют одно письмо дважды.
- Retention `email_outbox`: `EMAIL_OUTBOX_RETENTION_DAYS=30`; `sent`/`failed`
  архивируются в gzip-JSONL и удаляются, `pending` не затрагивается.
- Индекс `ix_email_outbox_status_next(status, next_attempt_at)` уже был в
  миграции `0035`; новых миграций нет.

### Observability Hardening (S-87)
- Логи Alertmanager проходят через `redact-logs.awk`: Telegram bot token и
  `Authorization: Bearer` маскируются, TTL логов — 14 дней.
- Второй receiver email включается при `SMTP_HOST` + `ALERT_EMAIL_TO`;
  маршруты `critical → telegram-critical,email` и `warning → telegram,email`
  независимы (`continue: true`).
- `node-exporter` и алерт `ChessClassObservabilityDiskFull` (<10% на
  `/var/tempo`).

### Certificate Rotation & Retention Ops (S-88)
- `scripts/check-cert-expiry.ps1`: проверка внутренних и edge-сертификатов,
  таблица `cert_path days_left status`, пороги 30/7 дней, exit 0/1/2,
  Telegram-алерт при warning/critical; soft-check в `scripts/ci.ps1`
  (warning не блокирует, critical блокирует).
- Ротация без простоя — `docs/runbooks/operations.md` §7.1: `-Force`,
  пересоздание `tempo`/`otel-collector`, mTLS-selftest, откат из копии,
  окно ≈30 секунд.
- Gauges `/metrics`: `chessclass_email_outbox_pending_total`,
  `chessclass_email_outbox_oldest_pending_age_seconds`,
  `chessclass_retention_archive_age_seconds`; алерты
  `ChessClassEmailOutboxStuck` и `ChessClassRetentionArchiveStale` (всего
  8 правил). Разбор — runbook §10.13.

### Юридический блокер снят (S-89)
- `docs/legal-review-v0.7.md`: раздел «Статус: ✅ Закрыто на уровне вне кода
  (решение юриста от 2026-11-08)»; все 16 вопросов — **Resolved**.
- Закрытие оформлено договорами, DPA/SCC, уведомлениями и организационными
  решениями; код и схема БД не менялись.
- Технические остаточные риски (тело письма в `email_outbox`, бэкапы/права
  субъекта) остаются под наблюдением и не являются юридическим блокером.

## Числа

- Backend: **310 collected** (307 passed + 3 skipped CSP-группы); ruff/mypy — 0.
- Frontend: Vitest **5 passed**, `tsc`/build — ок.
- UI-e2e: **16 сценариев** Playwright + axe.
- Observability selftest: **21/21 ok** (static + runtime, mTLS, email, gauges).
- Миграции: **35**, head `0035_s83_email_outbox`; новых миграций в v0.7.1 нет.
- RAG: 13/13; gold: 21/21; doc-lint: 6 checks, 0 failed.
- pip-audit: 0 известных уязвимостей.

## Обновление

```bash
git fetch --tags && git checkout v0.7.1
IMAGE_TAG=0.7.1 docker compose --env-file .env -f docker-compose.prod.yml up -d
docker compose --env-file .env -f docker-compose.prod.yml run --rm migrate
```

- Миграции не добавлялись; `alembic upgrade head` остаётся идемпотентным.
- Проверить env: `EMAIL_OUTBOX_MAX_ATTEMPTS`, `EMAIL_OUTBOX_RETENTION_DAYS`,
  `SMTP_*` (реальная доставка), `TELEGRAM_*` / `ALERT_EMAIL_TO` (алерты).
- Для observability — профиль и сертификаты:

  ```bash
  ./scripts/gen-internal-certs.ps1
  docker compose --env-file .env -f docker-compose.prod.yml \
    --profile observability up -d
  ./scripts/observability-selftest.ps1 -Stack
  ```

- Ротация сертификатов — `docs/runbooks/operations.md` §7.1; ежедневная
  проверка — `./scripts/check-cert-expiry.ps1`.

## Известные ограничения

- **Реальный prod-контур** не разворачивался в этом цикле: проверены Docker
  CI/e2e/observability-selftest, но не боевые SMTP/Telegram/edge-сертификаты.
- **S-81 (Live Staging Acceptance)** и **S-84 (GPU Tunnel)** остаются
  отложенными: нужны боевые ключи LRS/ElevenLabs и физическая станция
  RTX 3060 + LM Studio.
- **DevOps-аудит** выявил блокеры production-запуска (реальный IP за прокси,
  object-level authz, GHCR/Sentry/logrotate, SMTP, offsite-бэкапы, песочница).
  Они вынесены в `TODO_V0.8.md` (S-90…S-94).
- **Юридический статус** закрыт на уровне договорённостей; технические
  остаточные риски §7 `legal-review-v0.7.md` продолжают отслеживаться.
