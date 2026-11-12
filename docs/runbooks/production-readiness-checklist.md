# Чек-лист production-готовности ChessClass v1.0.1

**Назначение:** проверка перед первым запуском и перед каждым мажорным
релизом. `✅` — проверено в репозитории/локально, `⏳` — требует сервера или
боевых ключей, `❌` — блокер, устранить до запуска.

Ссылки: [production-deployment-v1.0.1.md](production-deployment-v1.0.1.md),
[operations.md](operations.md), `docs/release-notes-v1.0.1.md`.

## 1. Инфраструктура

| Проверка | Статус | Команда / ссылка |
|---|---|---|
| `docker-compose.prod.yml` валиден, без `build:` | ✅ | `docker compose --env-file .env.prod.example -f docker-compose.prod.yml config -q` |
| `IMAGE_TAG` из env, не хардкод | ✅ | compose/env — `1.0.1`, GHCR публикует semver `1.0.1` (P0-1) |
| `restart: unless-stopped` у сервисов | ✅ | кроме `migrate`/`seed` (`"no"`) — ожидаемо |
| Healthcheck'и | ✅ | db, redis, api, edge, tempo, prometheus, alertmanager; у `web` нет (P2) |
| Наружу только 80/443 | ✅ | `web` биндится на `127.0.0.1:${WEB_PORT:-3200}` (P1-1) |
| Миграции гейтом до api/worker | ✅ | `depends_on: migrate: service_completed_successfully` |
| `seed` не запускается сам | ✅ | профиль `tools` |
| Лимиты CPU/RAM | ❌ | `deploy.resources.limits` отсутствуют во всём compose |
| Сервер 4/8 (8/16) | ⏳ | см. §7 отчёта аудита |
| Docker 29+, Compose v2 | ⏳ | `docker version`, `docker compose version` |
| DNS A-запись на IP | ⏳ | `dig +short <domain>` |
| Порты 80/443 открыты | ⏳ | `ss -ltnp`, UFW |
| Swap ≥ 2 ГБ (при 8 ГБ) | ⏳ | `swapon --show` |

## 2. Безопасность

| Проверка | Статус | Команда / ссылка |
|---|---|---|
| RS256, `JWT_LEGACY_HS256=false` | ✅ | `.env.prod.example`, `/auth/jwks` |
| Ключи не в git, права 644 | ✅ | `deploy/jwt/.gitignore`, runbook §3 |
| Secrets scan | ✅ | CI gitleaks + `.gitleaksignore` для исторических false-positive (P2-1) |
| pip-audit | ✅ | `No known vulnerabilities` (osv) |
| Non-root в образе | ✅ | `USER appuser` (uid 1000) |
| Seccomp для sandbox | ✅ | `deploy/seccomp-sandbox.json` на api/worker/match-* |
| `PROXY_TRUSTED_HOSTS` только edge | ✅ | `172.16.0.0/12,127.0.0.1`; XFF теперь `$remote_addr` |
| Edge TLS 1.2/1.3, HSTS, CSP, 80→443 | ✅ | `deploy/nginx/edge.conf` |
| Автопродление TLS | ❌ | certbot в compose нет, cron в репо нет — runbook §4 |
| Алерт на срок сертификата | ❌ | `check-cert-expiry.ps1` есть, в cron/метрики не заведён |
| UFW/fail2ban | ❌ | `deploy/firewall/` отсутствует |
| Пароли/токены только в `.env` (600) | ⏳ | проверить на сервере |

## 3. Данные

| Проверка | Статус | Команда / ссылка |
|---|---|---|
| Named volumes для PG/Redis | ✅ | `chessclass_prod_pgdata`, `chessclass_prod_redisdata` |
| `POSTGRES_PASSWORD` из env | ✅ | `${POSTGRES_PASSWORD:?set in .env}` |
| `pgvector` создаётся миграцией | ✅ | `0001_initial_infra.py` |
| RLS-роль `chess_app` + `SET LOCAL ROLE` | ✅ | `0031_s72_rls_isolation`, `core/db.py` |
| Миграции = head `0036_s98_legal_hold` | ✅ | `/readyz`, doc-lint |
| Пул соединений vs `max_connections` | ❌ | `db_pool_size=10` × ~9 процессов ≈ 90 при лимите 100 (P1) |
| `shared_buffers`/`max_connections` тюнинг | ❌ | дефолты Postgres, в compose не заданы (P2) |
| Бэкап локальный по cron | ✅ | `deploy/cron/chessclass-backup` |
| Offsite-бэкап на Linux | ❌ | скрипт только PowerShell; cron-версии нет (P1) |
| Restore-дрилл | ⏳ | `backup-restore-test.ps1` / runbook §9 |
| Retention/lifecycle S3 30 дней | ⏳ | настроить правило на бакете |

## 4. Мониторинг

| Проверка | Статус | Команда / ссылка |
|---|---|---|
| 12 правил `ChessClass*` | ✅ | `deploy/observability/alerts.yml` |
| Алерты: API down, 5xx, latency, DLQ, email, retention, backup, disk | ✅ | — |
| Алерт на сертификат | ❌ | нет правила |
| mTLS collector↔Tempo | ✅ | `deploy/internal-certs`, `observability-selftest` |
| Static self-test | ✅ | `observability-selftest.ps1` (все проверки ok) |
| `-Stack` на сервере | ⏳ | нужен стенд и токены Telegram |
| Alertmanager без токена не стартует | ✅ | без Telegram — receiver `"null"`, без CrashLoop (P1-6) |
| `/admin/observability/alerts` без critical | ⏳ | после запуска |
| Grafana за edge `/grafana/` | ⏳ | вход по `GRAFANA_ADMIN_*` |

## 5. Интеграции

| Проверка | Статус | Команда / ссылка |
|---|---|---|
| SMTP-переменные в env | ✅ | `SMTP_*` присутствуют |
| SMTP-доставка + SPF/DKIM/DMARC | ⏳ | `smtp-smoke.ps1`, реальный ящик |
| `SMTP_FROM` = домен с SPF/DKIM | ⏳ | иначе spam/DMARC fail |
| LLM RouterAI | ⏳ | `llm_smoke.py --mode live` |
| GPU-туннель (reverse SSH) | ⏳ | `test-gpu-tunnel.ps1`, runbook llm-gateway §6 |
| LRS/TTS | ⏳ | S-95 отложен до v1.1.0 (решение владельца) |
| Sentry (опционально) | ⏳ | `SENTRY_DSN`, PII off |
| Telegram-бот | ⏳ | `TELEGRAM_BOT_TOKEN` |

## 6. Бэкапы и восстановление

| Проверка | Статус | Команда / ссылка |
|---|---|---|
| Offsite S3, AES-256 | ✅ | `backup-offsite.ps1` (Windows) / runbook §9 (Linux) |
| `BACKUP_ENCRYPTION_KEY` 32 hex | ⏳ | заполнить в `.env` |
| Lifecycle 30 дней | ⏳ | правило бакета |
| Restore в temp PG: users/alembic | ⏳ | `backup-restore-test.ps1` |
| Метрика `chessclass_backup_last_success_timestamp_seconds` | ✅ | экспортируется API |
| Алерт `ChessClassBackupFailed` (>25 ч) | ✅ | `alerts.yml` |
| Ключ age/openssl хранится вне сервера | ⏳ | менеджер секретов |

## 7. Чек-лист оператора из release notes v1.0.1

- [ ] ⏳ SMTP: SPF/DKIM/DMARC **pass**, письмо не в Spam.
- [ ] ⏳ S3 backup + restore: объект загружен/проверен, restore в temp PG —
      `users=10`, alembic совпадает.
- [ ] ⏳ RS256/JWKS: `/.well-known/jwks.json` отдаёт ключ, legacy HS256
      отклоняется.
- [ ] ⏳ `PROXY_TRUSTED_HOSTS`: реальный IP клиента в lockout/аудите, подмена
      `X-Forwarded-For` не проходит.
- [ ] ⏳ Sentry: DSN задан (опционально), PII off.
- [ ] ⏳ `staging-acceptance.ps1` → `exit=0`.

## 8. Итог

Запуск разрешён, когда:

1. закрыты все `❌` (P0/P1) либо есть письменное решение владельца об
   ограничении;
2. все `⏳` отмечены после проверки на сервере;
3. отчёт о приёмке сохранён в `docs/sprint-reports/`.
