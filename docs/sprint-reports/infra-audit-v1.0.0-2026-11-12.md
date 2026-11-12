# Инфраструктурный аудит ChessClass v1.0.0

**Дата:** 2026-11-12 · **Тип:** read-only аудит + операционные документы ·
**Версия:** v1.0.0 (`28505cb`, тег `v1.0.0`) · **Docker:** 29.9.3 (Windows,
Docker Desktop) · **Роль:** infra/SRE · **Продуктовый код не менялся.**

**Итог:** инфраструктура близка к запуску, но есть **2 блокера P0**,
**7 рисков P1** и **8 замечаний P2**. Без их устранения первый деплой либо
упадёт на `pull`, либо поднимется с молча отключёнными SMTP/бэкапами.

## 1. Что проверено и с каким результатом

| Проверка | Команда / файл | Результат |
|---|---|---|
| Prod-compose | `docker compose --env-file .env.prod.example -f docker-compose.prod.yml config -q` | ✅ exit 0 |
| Staging-compose | то же, `-f docker-compose.staging.yml` | ✅ exit 0 |
| Только `image:` в prod | `grep build:` | ✅ `build:` нет; GHCR + `IMAGE_TAG` |
| Healthcheck'и | compose | ✅ db/redis/api/edge/tempo/prometheus/alertmanager |
| Порты | compose | ⚠️ api loopback, web `0.0.0.0:3200`, obs loopback |
| Volume'ы | compose | ✅ PG/Redis — named; `jwt/certs/nginx` — bind `:ro` |
| Миграции-гейт | compose | ✅ `migrate → service_completed_successfully` |
| pgvector | `0001_initial_infra.py` | ✅ `CREATE EXTENSION` |
| RLS | `0031`, `core/db.py` | ✅ `chess_app` + `SET LOCAL ROLE` |
| Seccomp | compose | ✅ на api/worker/match-* |
| Non-root | `backend/Dockerfile` | ✅ `appuser` uid 1000, slim, bubblewrap |
| Edge TLS/HSTS/CSP/редирект | `deploy/nginx/edge.conf` | ✅ TLS 1.2/1.3, HSTS, 80→443, CSP в web |
| XFF | `edge.conf` | ✅ `$remote_addr` (после фикса v1.0.0) |
| TLS-сертификаты | `deploy/certs/`, scripts | ⚠️ manual certbot, авто-renew нет |
| Алерты | `deploy/observability/alerts.yml` | ✅ 12 правил; ❌ нет алерта на сертификат |
| Observability static | `observability-selftest.ps1` | ✅ все проверки ok |
| Doc-lint | `doc_lint.py --skip-tests-count` | ✅ 6 checks, 0 failed |
| Doc-lint `--tests-count auto` | — | ⚠️ без dev-зависимостей pytest недоступен (в CI проходит) |
| pip-audit | `pip-audit -r requirements.lock -s osv` | ✅ `No known vulnerabilities` |
| gitleaks | `gitleaks detect` (git) | ⚠️ 3 находки — все false-positive (см. P2) |
| GHCR | `docker manifest inspect` | ✅ `v1.0.0` есть; ❌ `1.0.0` — нет |

## 2. Блокеры P0

### P0-1. `IMAGE_TAG`: образы в GHCR — `v1.0.0`, compose тянет `1.0.0`

- `deploy`/CI публикует теги `:v1.0.0` и `:<sha>`
  (`IMAGE_TAG=${{ github.ref_name }}`).
- `docker-compose.prod.yml` и `.env.prod.example` используют
  `${IMAGE_TAG:-1.0.0}`.
- Проверено: `docker manifest inspect ghcr.io/iilmchat/chessclass-backend:v1.0.0`
  → ok, `:1.0.0` → `manifest unknown`.

**Следствие:** первый `docker compose pull` падает, деплой не начинается.
**Обход:** `IMAGE_TAG=v1.0.0` в `.env` (шаг 2 runbook'а).
**Исправить в v1.1.0:** привести дефолт к `v1.0.0` или публиковать без `v`.

### P0-2. `env_file` не читает `.env.prod` — SMTP/LRS/бэкап молча пустые

Сервисы получают файл через `env_file: ${ENV_FILE:-.env}` (required:
false). Команда в задаче — `cp .env.prod.example .env.prod` +
`--env-file .env.prod` — подставляет переменные **только в compose**, но не
в контейнеры. api при этом стартует (DATABASE_URL/JWT идут через
`x-backend-env`), а `SMTP_*`, `BACKUP_S3_*`, `LRS_*`, `TELEGRAM_*`,
`PROXY_TRUSTED_HOSTS` берутся из дефолтов → **верификация email отключена,
бэкапы не настроены, доверие прокси не задано**.

**Следствие:** «успешный» деплой с неработающей регистрацией и без
offsite-бэкапов.
**Обход:** файл должен называться `.env` (дефолт compose) либо запускать с
`ENV_FILE=.env.prod`. Зафиксировано в runbook §2.

## 3. Риски P1

| # | Риск | Детали | Где |
|---|---|---|---|
| P1-1 | Web опубликован наружу | `"${WEB_PORT:-3200}:80"` → `0.0.0.0:3200`; должен быть loopback | `docker-compose.prod.yml` |
| P1-2 | Нет лимитов CPU/RAM | `deploy.resources.limits` отсутствует у всех сервисов; Stockfish-worker может занять весь хост | compose |
| P1-3 | Пул БД ≈ лимиту соединений | `db_pool_size=10` × ~9 процессов ≈ 90 при `max_connections=100` (дефолт PG) | `core/config.py`, compose |
| P1-4 | TLS не продлевается автоматически | certbot в compose нет, cron/таймера в репо нет; алерта на срок сертификата нет | `deploy/certs/README.md` |
| P1-5 | Offsite-бэкап только PowerShell | cron делает только локальный `backup.sh`; `backup-offsite.ps1` на Linux без `pwsh` не запустить | `deploy/cron`, `scripts/` |
| P1-6 | Alertmanager не стартует без токенов | `alertmanager-render.sh` exit 1 без `TELEGRAM_BOT_TOKEN`/`TELEGRAM_ALERT_CHAT_ID`; в `.env.prod.example` они пусты | compose, `deploy/observability/prod` |
| P1-7 | Нет host-hardening артефактов | отсутствуют `deploy/firewall/` (UFW) и runbook по DNS; на новом сервере настраивается вручную | `deploy/` |

## 4. Замечания P2

1. **gitleaks:** 3 исторические находки — все ложные: строка лога
   `auth: JWT_LEGACY_HS256=true` в `main.py` (2 коммита) и fixture-токен в
   `observability-selftest.ps1`. CI сканирует диапазон и зелёный; локальный
   `detect` красный → нужен `.gitleaks.toml` allowlist.
2. **`server_name _;`** в edge — catch-all, нет проверки Host.
3. **`web` без healthcheck** (единственный сервис без проверки).
4. **`METRICS_TOKEN` пуст по умолчанию** — `/metrics` открыт на loopback.
5. **`operations.md` §17:** `BACKUP_EXPECTED_ALEMBIC=0035_s83_email_outbox`,
   фактический head — `0036_s98_legal_hold`.
6. **`.env.prod.example`:** `SMTP_HOST=smtp.example.com`,
   `SMTP_FROM=noreply@example.com` — example-значения без маркера
   `CHANGE_ME`, легко забыть заменить.
7. **Нет `-DryRun`** у `backup-restore-test.ps1`, `staging-acceptance.ps1`,
   `test-gpu-tunnel.ps1` — оператор не может проверить их без боевых данных.
8. **Нет `docs/runbooks/dns-setup.md`** — DNS-записи (A, SPF, DKIM, DMARC)
   описаны фрагментарно в SMTP/final-acceptance.

## 5. Что нельзя проверить без реального сервера

- DNS, Let's Encrypt (валидность выпуска и renewal), открытость 22/80/443,
  работа UFW/fail2ban.
- Реальная SMTP-доставка и SPF/DKIM/DMARC на боевом домене.
- S3-бакет, lifecycle, restore из offsite-дампа (нужны ключи и бакет).
- Prometheus/Alertmanager «в бою», доставка тестового алерта в Telegram.
- GPU-туннель `172.18.0.1:8035` и `tokens_per_second` на целевом хосте.
- Нагрузочный профиль (Stockfish-очереди) на 4/8 и 8/16.

Всё перечисленное вынесено в чек-лист (`production-readiness-checklist.md`)
как `⏳`.

## 6. Дефекты, найденные в коде (передать coding-агенту)

- **P0:** тег образа (`v1.0.0` vs `1.0.0`) — правка дефолта/публикации.
- **P1:** пул соединений и отсутствие лимитов — параметры конфигурации,
  не бизнес-логика.
- **P2:** `web` healthcheck; сертификатный алерт в `alerts.yml`.

Продуктовые роуты/сервисы/миграции не затрагивались.

## 7. Размещение стенда (рекомендация)

Фактическое состояние хостов на 2026-11-12:

| Хост | Ресурсы | Занято | Свободно | Роль |
|---|---|---|---|---|
| `89.108.70.62` | 8 vCPU / 7.9 ГБ | ruchating + tickets | ~6.0 ГБ | primary, критичный |
| `94.250.252.142` | 4 / 7.8 ГБ | workflow-builder prod | ~6.8 ГБ | prod WB |
| `62.109.1.230` | 4 / 7.8 ГБ | VetAssistant + monitoring | ~5.9 ГБ | резерв |
| `130.193.46.157` | 2 / 3.9 ГБ | dzenwriter | ~2.8 ГБ | Yandex, бонус до ~декабря |
| `176.109.109.121` | 2 / 4 ГБ | WB staging | — | **недоступен** (таймаут SSH) |

ChessClass: 4/8 минимум, 8/16 рекомендуется (Stockfish + 5 worker'ов).
Ни на одном действующем хосте нет 8 ГБ свободных.

**Рекомендация:**

1. **Staging** — отдельная ВМ 4/8. Cloud.ru `wf-staging-01` сейчас недоступен
   и всё равно мал (2/4). Если его удалили/освободили — переиспользовать
   площадку под chessclass-staging после увеличения до 4/8 (замена WB
   staging допустима: его приёмка завершена, prod WB живёт на
   `94.250.252.142`).
2. **Prod** — отдельная ВМ 4/8 (лучше 8/16), не совмещать с WB staging или
   другими prod: у chessclass CPU-пики от Stockfish и данные
   несовершеннолетних (отдельный blast radius, требование §6.5
   `PROJECTS-PROD-READINESS.md`).
3. **Не размещать** на `89.108.70.62` (primary) и `62.109.1.230` (резерв) —
   только если это осознанный пилот с жёсткими лимитами.
4. **Yandex Cloud** — бонус заканчивается в декабре; для постоянного прода
   лучше Cloud.ru/reg.cloud, Yandex — только staging на время бонуса.
5. **FirstVDS `62.109.1.230`** — резерв/failover, не основная площадка
   (риск «залипания» IP из общего пула, тикет #15012763).

## 8. Рекомендации для v1.1.0

1. Исправить тег образа (P0-1) и добавить в CI проверку
   `docker manifest inspect` для тега из `.env.prod.example` (P0-2 → тест
   конфигурации).
2. Ввести `deploy.resources.limits` для api/db/redis/worker'ов и
   `db_pool_size` ≤ 5, чтобы уложиться в `max_connections=100` (P1-2/3).
3. `WEB_PORT=127.0.0.1:3200` по умолчанию либо loopback-биндинг в compose
   (P1-1).
4. Автоматизация TLS: certbot-сервис или cron + `deploy-hook`, плюс правило
   алерта по сроку сертификата (P1-4).
5. Linux-версия offsite-бэкапа (`backup-offsite.sh`) и cron для неё +
   restore-test раз в неделю (P1-5).
6. `.gitleaks.toml` с allowlist на лог-строку `JWT_LEGACY_HS256` и
   fixture-токен (P2-1).
7. `deploy/firewall/` (UFW, fail2ban) и `docs/runbooks/dns-setup.md` (P1-7,
   P2-8).
8. `-DryRun` для restore/acceptance/gpu-скриптов (P2-7).
9. Синхронизировать `operations.md` §17 с актуальным head миграций (P2-5).
10. Добавить smoke «fresh deploy» в CI: `compose config` + manifest check +
    `doc_lint`.

## 9. Артефакты

- `docs/runbooks/production-deployment-v1.0.1.md` — пошаговый деплой
  (обновлён в v1.0.1: тег без `v`, `ENV_FILE`).
- `docs/runbooks/production-readiness-checklist.md` — чек-лист оператора.
- этот отчёт.

Коммит: ветка `docs/infra-audit-v1.0.0`.
