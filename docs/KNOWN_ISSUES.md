# Известные проблемы ChessClass (KI)

Файл заведён **2026-11-20** на факте HEAD `3f691b7` (v1.0.1).
Формат: `KI-XXX` — название, приоритет, статус, файлы, описание, решение.

Приоритеты: 🔴 Critical / 🟠 High / 🟡 Medium / 🟢 Low
Статусы: Open / In Progress / Fixed / Documented / Deferred / Won't Fix

**Источники фактов (не выдумываются):**
- `docs/sprint-reports/infra-audit-v1.0.0-2026-11-12.md` — 2 P0 (закрыты v1.0.1), 7 P1, 8 P2;
- `docs/legal-review-v0.7.md` § 7 — остаточные риски R-1…R-10;
- `TODO_V1.1.md` — отложенные спринты S-95, S-81, S-84;
- `.github/workflows/ci.yml`, `docker-compose.prod.yml`, `docs/runbooks/operations.md` — сверка на HEAD.

Правило «один факт — один источник»: подробности остаются в документах выше,
здесь — только номер, статус и ссылка.

---

### KI-001 — Нет лимитов CPU/RAM у сервисов prod compose
- **Приоритет:** 🟠 High | **Статус:** Fixed | **Исправлено в:** KI-S01 (2026-11-20) | **Обнаружено:** 2026-11-12 (аудит P1-2)
- **Файлы:** `docker-compose.prod.yml`
- **Описание:** `deploy.resources.limits` отсутствует у api/db/redis/worker'ов;
  Stockfish-воркер может занять весь хост (4/8 — минимальный профиль).
- **Решение:** задать `deploy.resources.limits` для всех сервисов, проверить
  `docker compose config`.
- **Связанные:** KI-002, KI-005.

### KI-002 — Пул БД ≈ лимиту соединений PostgreSQL
- **Приоритет:** 🟠 High | **Статус:** Fixed | **Исправлено в:** KI-S01 (2026-11-20) | **Обнаружено:** 2026-11-12 (аудит P1-3)
- **Файлы:** `backend/app/core/config.py`, `docker-compose.prod.yml`
- **Описание:** `db_pool_size=10` × ~9 процессов ≈ 90 при `max_connections=100`
  (дефолт PG). При росте воркеров — `too many clients`.
- **Решение:** `db_pool_size ≤ 5` и/или явно поднять `max_connections` в compose.
- **Связанные:** KI-001.

### KI-003 — TLS не продлевается автоматически, нет алерта на срок сертификата
- **Приоритет:** 🟠 High | **Статус:** Fixed | **Исправлено в:** KI-S01 (2026-11-20) | **Обнаружено:** 2026-11-12 (аудит P1-4)
- **Файлы:** `deploy/certs/README.md`, `deploy/observability/alerts.yml`
- **Описание:** certbot-сервис/cron отсутствуют; в alerts.yml нет правила на
  срок сертификата (скрипт `check-cert-expiry.ps1` есть, но только вручную).
- **Решение:** certbot + deploy-hook либо cron продления, алерт critical/warning.
- **Связанные:** KI-005.

### KI-004 — Offsite-бэкап только на PowerShell
- **Приоритет:** 🟠 High | **Статус:** Fixed | **Исправлено в:** KI-S01 (2026-11-20) | **Обнаружено:** 2026-11-12 (аудит P1-5)
- **Файлы:** `deploy/cron/`, `scripts/backup-offsite.ps1`
- **Описание:** cron делает только локальный `backup.sh`; `backup-offsite.ps1`
  на Linux без `pwsh` не запускается → offsite-копии на prod нет.
- **Решение:** Linux-версия `backup-offsite.sh` + cron + еженедельный restore-test.
- **Связанные:** KI-014.

### KI-005 — Нет артефактов host-hardening (UFW, DNS runbook)
- **Приоритет:** 🟡 Medium | **Статус:** Open | **Обнаружено:** 2026-11-12 (аудит P1-7)
- **Файлы:** `deploy/`, `docs/runbooks/`
- **Описание:** отсутствуют `deploy/firewall/` (UFW/fail2ban) и
  `docs/runbooks/dns-setup.md`; на новом сервере настраивается вручную.
- **Решение:** добавить конфиги UFW/fail2ban и runbook DNS (A/SPF/DKIM/DMARC).
- **Связанные:** KI-012.

### KI-006 — `server_name _;` — catch-all без проверки Host
- **Приоритет:** 🟡 Medium | **Статус:** Open | **Обнаружено:** 2026-11-12 (аудит P2-2)
- **Файлы:** `deploy/nginx/edge.conf`
- **Описание:** edge принимает любой Host; при unknown-host возможен обход части
  проверок и неверные redirect'ы.
- **Решение:** явный `server_name` домена + отдельный default_server с 444.
- **Связанные:** KI-005.

### KI-007 — `web` без healthcheck в prod compose
- **Приоритет:** 🟢 Low | **Статус:** Open | **Обнаружено:** 2026-11-12 (аудит P2-3)
- **Файлы:** `docker-compose.prod.yml`
- **Описание:** единственный сервис без healthcheck; сбой web не виден в статусе стека.
- **Решение:** добавить healthcheck на `/` с `start_period`.
- **Связанные:** —

### KI-008 — `METRICS_TOKEN` пуст по умолчанию
- **Приоритет:** 🟢 Low | **Статус:** Open | **Обнаружено:** 2026-11-12 (аудит P2-4)
- **Файлы:** `docker-compose.prod.yml`, `.env.prod.example`
- **Описание:** `/metrics` на loopback без токена — любой локальный процесс видит метрики.
- **Решение:** обязательный токен в `.env.prod.example` + проверка в compose.
- **Связанные:** —

### KI-009 — `operations.md` ссылается на устаревшую ревизию Alembic
- **Приоритет:** 🟡 Medium | **Статус:** Open | **Обнаружено:** 2026-11-12 (аудит P2-5)
- **Файлы:** `docs/runbooks/operations.md`, `docs/development/…` (head)
- **Описание:** `BACKUP_EXPECTED_ALEMBIC=0035_s83_email_outbox`, фактический head —
  `0036_s98_legal_hold`; проверка бэкапа в runbook всегда упадёт.
- **Решение:** обновить константу до 0036 и добавить doc-lint-проверку head.
- **Связанные:** KI-004.

### KI-010 — Example-значения SMTP без маркера `CHANGE_ME`
- **Приоритет:** 🟢 Low | **Статус:** Open | **Обнаружено:** 2026-11-12 (аудит P2-6)
- **Файлы:** `.env.prod.example`, `.env.staging.example`
- **Описание:** `SMTP_HOST=smtp.example.com`, `SMTP_FROM=noreply@example.com` —
  легко забыть заменить, письма уходят в никуда.
- **Решение:** добавить `CHANGE_ME` и fail-fast проверку в smoke.
- **Связанные:** KI-015.

### KI-011 — Нет `-DryRun` у операционных скриптов
- **Приоритет:** 🟢 Low | **Статус:** Open | **Обнаружено:** 2026-11-12 (аудит P2-7)
- **Файлы:** `scripts/backup-restore-test.ps1`, `scripts/staging-acceptance.ps1`,
  `scripts/test-gpu-tunnel.ps1`
- **Описание:** оператор не может проверить сценарий без боевых данных/ключей.
- **Решение:** добавить `-DryRun` с проверкой конфигурации без сайд-эффектов.
- **Связанные:** KI-005.

### KI-012 — Нет CI-проверки `docker manifest inspect` для IMAGE_TAG
- **Приоритет:** 🟡 Medium | **Статус:** Open | **Обнаружено:** 2026-11-12 (аудит §8.1)
- **Файлы:** `.github/workflows/ci.yml`, `.env.prod.example`
- **Описание:** P0-1 (тег v1.0.0 vs 1.0.0) закрыт в v1.0.1, но гейта, который
  ловит расхождение тега образа и `IMAGE_TAG`, нет — баг может вернуться.
- **Решение:** шаг `docker manifest inspect ghcr.io/...:${IMAGE_TAG}` в CI/CD.
- **Связанные:** —

### KI-013 — Тело письма в `email_outbox` хранит одноразовую ссылку открыто
- **Приоритет:** 🟠 High | **Статус:** Deferred | **Обнаружено:** 2026-11-08 (legal R-1)
- **Файлы:** `backend/app/...`, `docs/legal-review-v0.7.md` § 7
- **Описание:** при утечке БД подтверждение согласия без родителя в течение TTL.
  Юридическим блокером не является, отслеживается отдельно.
- **Решение:** шифрование/маскирование, короткий TTL, инвалидация pending.
- **Связанные:** KI-014.

### KI-014 — Бэкапы и DSAR не проверены на реальном сервере
- **Приоритет:** 🟠 High | **Статус:** Deferred | **Обнаружено:** 2026-11-08 (legal R-8)
- **Файлы:** `docs/legal-review-v0.7.md` § 7, `scripts/backup-restore-test.ps1`
- **Описание:** нет факта восстановления и полного исполнения прав субъекта
  на боевом контуре; требуется доступ к серверу/бакету.
- **Решение:** провести restore-drill и DSAR-проверку, зафиксировать отчёт.
- **Связанные:** KI-004, KI-013.

### KI-015 — Live LRS/TTS (S-95) — нет боевых ключей
- **Приоритет:** 🟠 High | **Статус:** Deferred | **Обнаружено:** 2026-11-12
- **Файлы:** `TODO_V1.1.md` S-95
- **Описание:** нельзя проверить OAuth2/квоты/rate-limit LRS, TTS и реальную
  SMTP-доставку без ключей ElevenLabs/LRS и доменной почты. Контракты и fallback
  покрыты моками.
- **Решение:** получить ключи, провести live-приёмку, отчёт S-95.
- **Связанные:** KI-010.

### KI-016 — GPU-туннель/станция (S-84) — нет физической станции
- **Приоритет:** 🟡 Medium | **Статус:** Deferred | **Обнаружено:** 2026-11-07
- **Файлы:** `TODO_V0.7.md` S-84, `scripts/test-gpu-tunnel.ps1`
- **Описание:** нет целевого хоста с GPU для проверки туннеля и throughput.
- **Решение:** выделить станцию, проверить `tokens_per_second`, закрыть ADR.
- **Связанные:** KI-011.

### KI-017 — Live staging-приёмка (S-81) отложена
- **Приоритет:** 🟡 Medium | **Статус:** Deferred | **Обнаружено:** 2026-11-07
- **Файлы:** `TODO_V0.7.md` S-81
- **Описание:** зависит от боевых ключей LRS/TTS и доступности/staging-ВМ.
- **Решение:** после KI-015/KI-016 провести приёмку по чек-листу.
- **Связанные:** KI-015, KI-016.

### KI-018 — Алерт на срок сертификата отсутствует (дубль KI-003)
- **Приоритет:** 🟢 Low | **Статус:** Fixed | **Исправлено в:** docs-only 2026-11-20
- **Файлы:** `docs/KNOWN_ISSUES.md`
- **Описание:** в аудите вынесен отдельной строкой §6; объединён с KI-003 как
  одна проблема «TLS renewal + alert», чтобы не дублировать работу.
- **Связанные:** KI-003.
- **Fix:** в `docker-compose.prod.yml` добавлены якоря `x-resources-*` и `deploy.resources.limits` для db/redis/api/воркеров/web/edge; `docker compose config -q` проходит.
- **Fix:** дефолт `db_pool_size` снижен с 10 до 5 (`backend/core/config.py`) — ~45 соединений при 9 процессах укладываются в 100.
- **Fix:** cron пишет метрику `chessclass_tls_cert_expiry_days` в textfile-collector node-exporter (`scripts/write-cert-metric.sh`, `deploy/cron/chessclass-cert-metric`, volume `chessclass_cert_metrics`); добавлены алерты <30 и <7 дней в `alerts.yml`.
- **Fix:** добавлены `scripts/backup-offsite.sh` (Linux, совместим с PowerShell-версией по openssl/S3/статусу) и cron `deploy/cron/chessclass-offsite-backup`; синтаксис проверен в bash:5.2, `--dry-run` работает.

---

## Сводка по статусам

Пересчитано grep'ом на 2026-11-20: **18** заголовков `### KI-`, **18** строк статуса.

| Статус | Количество |
|---|---:|
| Open | 8 |
| Deferred | 5 |
| Fixed | 5 |
| Documented | 0 |
| **Итого** | **18** |
