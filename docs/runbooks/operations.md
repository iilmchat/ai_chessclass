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
- Ротация `SMTP_PASSWORD`: обновить `.env`, пересоздать `alertmanager`
  (email-receiver, §10.11) и `worker` (email outbox); проверить тестовым
  алертом/письмом.
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

## 7. Плановые проверки и ротация сертификатов

### 7.1. Ротация внутренних сертификатов без простоя (S-88)

Внутренний CA и mTLS-сертификаты (`deploy/internal-certs/`: `ca`, `tempo`,
`collector`) перевыпускаются `scripts/gen-internal-certs.ps1`. Ротация
затрагивает только связку collector → Tempo: API, worker, web, edge, Prometheus,
Alertmanager и Grafana продолжают работать. Короткий простой **≈30 секунд**
допустим: на это время Tempo/collector недоступны, spans теряются (traces —
best-effort), бизнес-запросы и почта/алерты не страдают.

1. **Проверить текущий срок и снять копию.** Копия нужна для отката: каталог
   исключён из git (`.gitignore`), поэтому старые файлы не восстановятся
   командой `git checkout`.

   ```powershell
   .\scripts\check-cert-expiry.ps1
   $stamp = Get-Date -Format "yyyyMMddTHHmmssZ"
   New-Item -ItemType Directory -Force "backups/internal-certs-$stamp" | Out-Null
   Copy-Item deploy/internal-certs/* "backups/internal-certs-$stamp/" -Force
   ```

   `check-cert-expiry.ps1` печатает таблицу `cert_path days_left status`:
   exit 0 — всё ok, 1 — warning (< 30 дней), 2 — critical (< 7 дней или файл
   не читается). При warning/critical и заданных `TELEGRAM_BOT_TOKEN` +
   `TELEGRAM_ALERT_CHAT_ID` скрипт отправляет сообщение в Telegram.

2. **Перевыпустить сертификаты.**

   ```powershell
   .\scripts\gen-internal-certs.ps1 -Force
   ```

   Скрипт пересоздаёт CA, `tempo.crt/key` и `collector.crt/key`, SAN
   `tempo`/`otel-collector`/`localhost`; ключи не коммитить.

3. **Пересоздать Tempo и collector** (не просто restart: они читают файлы при
   старте, а конфиг mTLS ссылается на смонтированный каталог):

   ```bash
   docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
     up -d --force-recreate tempo otel-collector
   docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
     ps tempo otel-collector
   ```

   Ожидаемо: оба контейнера `running`/`healthy`; в логах нет
   `x509`/`certificate`/`permission denied`:

   ```bash
   docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
     logs --tail=100 tempo otel-collector
   ```

4. **Проверить mTLS-трейс и маршруты алертов.**

   ```powershell
   .\scripts\observability-selftest.ps1 -Stack
   .\scripts\check-cert-expiry.ps1
   ```

   Selftest отправляет тестовый OTLP-трейс через `collector.crt`/`ca.crt`,
   читает его из Tempo и проверяет маршруты Alertmanager; в конце он
   останавливает только контейнеры профиля (volumes сохраняются). Точечная
   проверка маршрутов — §10.6, п. 4 (ожидаемо `telegram-critical,email` для
   critical и `telegram,email` для warning).

5. **Откат**, если mTLS не поднимается (collector пишет TLS/x509, selftest
   «mTLS: трейс принимается Tempo» падает):

   ```powershell
   Copy-Item "backups/internal-certs-$stamp/*" deploy/internal-certs/ -Force
   ```

   ```bash
   docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
     up -d --force-recreate tempo otel-collector
   ```

   Затем повторить п. 4. `git checkout -- deploy/internal-certs/` применим
   только если сертификаты были закоммичены в вашей ветке (нештатно): штатно
   каталог в `.gitignore`, и git его не восстанавливает. Копию из
   `backups/internal-certs-$stamp/` удалить после 24 часов успешной работы.

### 7.2. Регулярные проверки

- Ежедневно: backup task + `.\scripts\check-cert-expiry.ps1` (warning/critical
  → Telegram; critical в CI блокирует сборку).
- Еженедельно: `restore-test`, `smoke-prod.ps1`, `GET /admin/matches/metrics`,
  `GET /admin/llm/health`.
- Перед релизом: backend CI (ruff/mypy/pytest), frontend build, Playwright
  e2e (`.\scripts\e2e.ps1 test`), `check-cert-expiry.ps1`, prod smoke.

## 8. Retention и наблюдаемость (S-46)

- Retention (cron 04:10 UTC / вручную):
  `POST /admin/observability/retention/run` (`{"dryRun": true}` — проверка).
  Политики: audit 365 дн., llm_calls 180, voice 30, draft/rejected studies 90;
  перед удалением — gzip-архив в `RETENTION_ARCHIVE_DIR` (prod volume
  `chessclass_archive`). Published studies не удаляются.
- `GET /metrics` — Prometheus (DB/Redis, очереди, LLM/voice cost, диск).
  В prod задайте `METRICS_TOKEN` и scrape только из внутренней сети.
- `GET /admin/observability/summary|alerts|costs|costs.csv|retention/status` —
  админ-дашборд `/ops`; алерты: DB/Redis, диск, очередь, LLM-cost, TLS,
  устаревший retention.
- Проверка после retention: `restore-test` на свежем бэкапе (S-38).

## 9. JWT-ключи и PII (S-47)

- HS256 по умолчанию (`JWT_SECRET`); для RS256:
  `.\scripts\gen-jwt-keys.ps1 -Force` → `deploy/jwt/{private,public}.pem`,
  затем `JWT_ALGORITHM=RS256`, `JWT_PRIVATE_KEY_PATH=/srv/jwt/private.pem`,
  `JWT_PUBLIC_KEY_PATH=/srv/jwt/public.pem`, `JWT_KID=v1`.
  Перезапустить api; JWKS: `/api/v1/auth/jwks`,
  `/.well-known/jwks.json`. С S-90 `JWT_LEGACY_HS256=false` по умолчанию;
  `true` — только переходный период (в prod/staging даёт startup-warning).
- Ротация: новый `kid`/ключи, оставить старый public key на время TTL
  (15 мин), затем убрать; ключи не коммитить (`.gitignore`).
- Аудит: `auth.login.success/failed`, `auth.role.change`,
  `auth.auditor_scope.change`, `auth.user.anonymize` — в `audit_logs`.
- Auditor scope: `flags|audit|reports|observability`; admin —
  `PATCH /admin/users/{id}/auditor-scope`; teacher/admin не ограничены.
- PII/право на забвение: `POST /admin/users/{id}/anonymize` — anon-email,
  случайный пароль, display_name «Удалённый пользователь», age_group
  unknown, refresh отозваны; учебные записи сохраняются для аудита.
  `age_group` — только самооценка/teacher, без даты рождения.
- Security-проверки: `python -m pytest tests/test_auth_hardening.py -q`;
  refresh reuse уже покрыт `test_auth_flow.py`.

## 10. Prod-observability (S-82)

Профиль `observability` в `docker-compose.prod.yml`: OTel Collector → Tempo
(traces) и Prometheus (metrics) → Grafana; правила Prometheus → Alertmanager
→ Telegram. Dev-контур S-77 (те же компоненты локально) — в
`deploy/observability/README.md`, prod-конфиги — в `deploy/observability/prod/`.
Здесь — эксплуатация профиля: запуск, проверки, действия по алертам. Состав и
значения конфигов не дублируются: источник — файлы в `deploy/observability/`
и `docker-compose.prod.yml`.

### 10.1. Состав профиля

| Сервис | Контейнер | Доступ | Роль |
|---|---|---|---|
| `tempo` | `chessclass-prod-tempo` | только внутри сети, наружу портов нет | хранение traces; volume `chessclass_prod_tempo` |
| `otel-collector` | `chessclass-prod-otel-collector` | OTLP внутри сети: `otel-collector:4318` (HTTP), gRPC `:4317`; health `:13133` | приём spans от api/worker |
| `node-exporter` | `chessclass-prod-node-exporter` | только внутри сети `:9100` | метрики файловых систем volumes observability (S-87) |
| `prometheus` | `chessclass-prod-prometheus` | `127.0.0.1:${PROMETHEUS_PORT:-9092}` | scrape `/metrics`, правила `deploy/observability/alerts.yml` |
| `alertmanager` | `chessclass-prod-alertmanager` | `127.0.0.1:${ALERTMANAGER_PORT:-9093}` | группировка и доставка в Telegram, silences |
| `grafana` | `chessclass-prod-grafana` | `https://<host>/grafana/` через `edge`; loopback `${GRAFANA_PORT:-3002}` | дашборды, запросы в Tempo/метрики |

Профиль **не стартует по умолчанию**: обычный `up -d` поднимает только базовый
стек (db, redis, migrate, api, worker*, web, edge). Без профиля нет traces и
нет алертов: API продолжает отдавать `/metrics`, но собирать его некому.
Traces не экспортируются, пока `OTEL_ENABLED` не `true`, а endpoint не задан.

### 10.2. Подготовка prod-env и сертификатов

1. **prod-env.** Переменные задаются в одном prod-файле (`.env`; шаблон —
   `.env.prod.example`, на сервере `cp .env.prod.example .env`; в командах
   ниже `--env-file .env`). Не дублируйте значения между `.env` и
   `.env.prod`.

   | Переменная | Значение | Комментарий |
   |---|---|---|
   | `OTEL_ENABLED` | `true` | включает экспорт spans из api/worker |
   | `OTEL_SERVICE_NAME` | `chessclass-api` | имя сервиса в Tempo |
   | `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | OTLP/HTTP внутри compose-сети |
   | `GRAFANA_ADMIN_USER` | `chessadmin` | логин администратора; сменить при первом запуске |
   | `GRAFANA_ADMIN_PASSWORD` | `CHANGE_ME` | обязателен: при пустом значении Grafana не стартует |
   | `GRAFANA_ROOT_URL` | `https://<host>/grafana/` | внешний URL за edge (подпуть `/grafana/`) |
   | `PROMETHEUS_PORT` | `9092` | loopback-порт Prometheus |
   | `ALERTMANAGER_PORT` | `9093` | loopback-порт Alertmanager |
   | `GRAFANA_PORT` | `3002` | loopback-порт Grafana для отладки |
   | `TELEGRAM_BOT_TOKEN` | `CHANGE_ME` | токен бота дежурного чата, только в prod-env |
   | `TELEGRAM_ALERT_CHAT_ID` | `-100…` | id чата/канала (у групп и каналов отрицательный); пусто → Alertmanager не стартует |
   | `ALERT_EMAIL_TO` | `duty@…` | второй канал (email); включается вместе с `SMTP_HOST` из §5 |
   | `ALERT_TELEGRAM_API_URL` | `https://api.telegram.org` | только для selftest/отладки; в prod оставить default |
   | `METRICS_TOKEN` | `CHANGE_ME` | bearer-токен для scrape `/metrics`; одно значение для api и Prometheus |

2. **Внутренние сертификаты TLS** (collector → Tempo, mTLS):

   ```powershell
   .\scripts\gen-internal-certs.ps1
   ```

   Скрипт создаёт внутренний CA и сертификаты в `deploy/internal-certs/`
   (CA, серверный сертификат Tempo, клиентский сертификат collector).
   Каталог не в git; приватные ключи не копировать в чаты и бэкапы
   репозитория. Сертификаты нужны до первого запуска профиля; после
   перегенерации — плановая ротация по §7.1 (пересоздание `tempo`/
   `otel-collector`, проверка mTLS и откат).
   Контейнеры Tempo и collector работают не от root, но ключи им должны быть
   читаемы; при ошибке `permission denied` на `/etc/obs-certs/*.key` — смотреть
   права каталога и монтирования сертификатов.

3. **Секреты до запуска.**

   ```bash
   git check-ignore -v .env .env.prod deploy/internal-certs/ca.key
   ```

   Команда должна показать совпадения: prod-env и ключи внутреннего CA
   исключены из git (см. §10.9).

4. **Egress.** Для доставки алертов с сервера должен быть доступен
   `api.telegram.org` (или `telegram_api_url` из шаблона Alertmanager); если
   сервер за allowlist/firewall — добавить домен заранее, иначе алерты
   не уйдут.

### 10.3. Запуск, остановка, логи

```bash
cd /opt/chessclass
docker compose --env-file .env -f docker-compose.prod.yml --profile observability up -d
```

Порядок запуска задан зависимостями в compose: tempo → otel-collector →
prometheus и alertmanager → grafana; отдельные команды не нужны. Первый
запуск создаёт volumes `chessclass_prod_tempo`, `chessclass_prod_prometheus`
и другие.

Статус и здоровье:

```bash
docker compose --env-file .env -f docker-compose.prod.yml --profile observability ps
```

Ожидаемо: контейнеры `running`; у сервисов с healthcheck — `healthy` (первые
секунды после старта — `starting`). `unhealthy`/`restarting` — смотреть логи
сервиса. Типичные причины `restarting` при первом запуске: пустой
`TELEGRAM_ALERT_CHAT_ID` (Alertmanager не стартует осознанно), недоступные
контейнеру ключи `/etc/obs-certs/*.key` (Tempo/collector), ошибка TLS-конфига
Tempo в его логах.

Логи:

```bash
docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
  logs --tail=200 tempo
# то же для otel-collector, prometheus, alertmanager, grafana
```

Остановка. Данные сохраняются в volumes:

```bash
# погасить только наблюдаемость (API/edge продолжают работать)
docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
  stop tempo otel-collector prometheus alertmanager grafana

# снять контейнеры всего prod-стека вместе с профилем (штатная полная остановка)
docker compose --env-file .env -f docker-compose.prod.yml --profile observability down
```

> **Внимание.** `down` с профилем удаляет контейнеры всего проекта, включая
> базовые (api/edge/db), — это полная остановка prod, а не только
> наблюдаемости. Для остановки одной наблюдаемости используйте `stop` с
> перечислением сервисов. Ключ `-v` дополнительно удаляет volumes с traces и
> метриками: при инциденте данные нужны для разбора, `down -v` не применять.

### 10.4. Адреса и доступ

| Что | Адрес | Примечание |
|---|---|---|
| Grafana (дежурство) | `https://<host>/grafana/` | только VPN/доверенная сеть, TLS на `edge` |
| Grafana (отладка) | `http://127.0.0.1:${GRAFANA_PORT:-3002}` | только с самого сервера или через SSH-туннель |
| Prometheus | `http://127.0.0.1:${PROMETHEUS_PORT:-9092}` | UI: `/graph`, `/alerts`, `/rules`, `/targets` |
| Alertmanager | `http://127.0.0.1:${ALERTMANAGER_PORT:-9093}` | UI и API v2: `/api/v2/status`, `/api/v2/alerts` |
| OTLP для api/worker | `http://otel-collector:4318` | только внутри compose-сети, с хоста не публикуется |
| Tempo | внутри сети, через Grafana | наружу портов не публикует; UI/API — из Grafana |

Если loopback-порты нужны с рабочей машины:

```bash
ssh -L 9092:127.0.0.1:9092 -L 9093:127.0.0.1:9093 -L 3002:127.0.0.1:3002 <user>@<host>
```

### 10.5. Проверка готовности

```bash
curl -s http://127.0.0.1:9092/-/ready        # Prometheus Server is Ready.
curl -s http://127.0.0.1:9093/-/ready        # OK
curl -s http://127.0.0.1:3002/api/health     # {"database":"ok",...}
curl -s http://127.0.0.1:9092/api/v1/rules   # 12 правил ChessClass*
curl -s http://127.0.0.1:9093/api/v2/status  # cluster/version/config
```

- `/api/v1/rules` пуст или в rules нет `ChessClassHighErrorRate` — Prometheus
  не увидел `deploy/observability/alerts.yml`; проверить prod-конфиг
  Prometheus и его логи.
- `curl -s http://127.0.0.1:9092/api/v1/targets` — target `chessclass-api`
  должен быть `up`; если `down`, проверить `METRICS_TOKEN` (значение одно для
  api и Prometheus) и доступность `api:8020/metrics`.
- Collector: health-расширение слушает `:13133` (порт внутренний). Если в
  compose задан healthcheck — статус в `docker compose ps` (подробно —
  `docker inspect --format '{{.State.Health.Status}}' chessclass-prod-otel-collector`);
  независимая проверка — target `otel-collector` в Prometheus `/api/v1/targets`
  (`up`) и отсутствие ошибок TLS/экспорта в логах collector.
- Traces: Grafana → Explore → Tempo → поиск по `trace_id` из логов API или
  `llm_calls.trace_id`. Пусто — проверить `OTEL_ENABLED`, endpoint collector и
  логи `tempo`/`otel-collector` (TLS-ошибки сертификатов видны там).
- Список активных алертов:

  ```bash
  docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
    exec alertmanager amtool alert query --alertmanager.url=http://127.0.0.1:9093
  ```

  `--alertmanager.url=http://127.0.0.1:9093` можно не указывать внутри
  контейнера Alertmanager.

### 10.6. Проверка доставки алертов (Telegram + email)

Telegram-чат дежурного получает алерты от Alertmanager; `chat_id` — `-100…`
(заглушка), токен бота — только в prod-env. Проверка — тестовым алертом,
который через 5 минут сам станет `resolved` (проверяет и `send_resolved`).
Если `TELEGRAM_BOT_TOKEN` или `TELEGRAM_ALERT_CHAT_ID` пусты, Alertmanager не
стартует (в `docker compose ps` — `restarting`) — это осознанно, чтобы не
терять алерты молча.

1. **Отправить тестовый алерт** (5 минут, затем авто-resolved):

   ```bash
   docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
     exec alertmanager amtool alert add ChessClassTestAlert \
     severity=warning component=observability \
     --annotation=summary='Проверка доставки алертов' \
     --annotation=description='Тестовое уведомление из runbook operations §10' \
     --start="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     --end="$(date -u -d '+5 min' +%Y-%m-%dT%H:%M:%SZ)" \
     --alertmanager.url=http://127.0.0.1:9093
   ```

2. **Убедиться, что алерт принят и доставлен:**

   ```bash
   docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
     exec alertmanager amtool alert query --alertmanager.url=http://127.0.0.1:9093
   docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
     logs --tail=100 alertmanager
   ```

   В чате — сообщение `firing` (severity/warning, alertname, summary,
   description, job), через ~5 минут — `resolved`. В логах Alertmanager —
   строка `notify success` (доставлено) или `notify failed` (причина).

3. **Если сообщение не пришло** — по порядку:

   - `.env` на сервере: `TELEGRAM_BOT_TOKEN` и `TELEGRAM_ALERT_CHAT_ID`
     заполнены (не пустые, без кавычек/пробелов). Конфиг рендерится из
     шаблона при старте контейнера, поэтому после правки `.env` нужно
     **пересоздать** контейнер, а не просто перезапустить:
     `up -d --force-recreate alertmanager`.
   - `TELEGRAM_ALERT_CHAT_ID` — id чата/канала (`-100…`); для группы бот
     должен быть участником, для канала — администратором; бот не заблокирован
     пользователем. Проверка бота: `curl -s "https://api.telegram.org/bot<TOKEN>/getMe"`
     (токен не выводить в чаты/тикеты), для чата —
     `.../bot<TOKEN>/getChat?chat_id=<chat_id>`.
   - Egress: `api.telegram.org` (или `telegram_api_url` из шаблона) доступен с
     сервера/из сети Alertmanager — проверить firewall/allowlist (§10.2, п. 4).
   - Шаблон сообщения `deploy/observability/prod/telegram.tmpl` и маршруты —
     в prod-конфиге Alertmanager; ошибка рендера шаблона видна как
     `notify failed` в логах. Правки — только через репозиторий.
   - `send_resolved: true` — если `firing` пришёл, а `resolved` нет, проверить
     этот параметр и `resolve_timeout` в prod-конфиге Alertmanager.

4. **Второй канал (email).** Если в `.env` заданы `SMTP_HOST` и
   `ALERT_EMAIL_TO`, тот же алерт уходит на email независимо от Telegram
   (§10.11). Проверка маршрута:

   ```bash
   docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
     exec alertmanager amtool config routes test \
     severity=critical alertname=ChessClassTestAlert component=observability \
     --config.file=/tmp/alertmanager.yml
   ```

   Ожидаемо: `telegram-critical,email` (для warning — `telegram,email`).
   Письмо придёт на `ALERT_EMAIL_TO`; если его нет — смотреть
   `logs alertmanager` по `integration=email`, проверить `SMTP_HOST/PORT`
   (нужен STARTTLS, обычно 587; implicit TLS 465 не поддерживается),
   `SMTP_USER/PASSWORD` и доступность SMTP с сервера.

### 10.7. Алерт → что делать

Условия, пороги и метки — в `deploy/observability/alerts.yml`; ниже — первые
шаги дежурного, диагностика и эскалация — в `docs/incident-response.md` §4.1.

| Алерт | Суть | Первые шаги |
|---|---|---|
| `ChessClassApiDown` | API не скрейпится (`up == 0`) | `docker compose ... ps api`; `curl -s http://127.0.0.1:8020/healthz` и `/readyz`; логи `api`; БД/Redis; внешний `https://<host>/healthz`; при падении — рестарт `api` и проверка §6 |
| `ChessClassHighErrorRate` | >5% HTTP 5xx за 5 минут | `/ops`, логи `api` по `request_id`, всплеск 5xx в `/metrics`; trace в Tempo; проверить БД/Redis/диск/LLM-провайдера; причина и действия — §6 |
| `ChessClassP95LatencyHigh` | p95 > 2 с | Grafana: p95 по route; самые медленные traces в Tempo; БД (медленные запросы, пул соединений), LLM-таймауты, очередь |
| `ChessClassDLQGrowth` | `chessclass_failed_jobs > 10` | `/ops` → DLQ; причина падений задач; логи `worker`; разобрать и повторить задачи; не чистить очередь без разбора |
| `ChessClassDLQGrowthRate` | быстрый рост DLQ | как `DLQGrowth`; проверить конкретный тип задач (analyze/pdf/матчи), свежий деплой/зависимость |
| `ChessClassObservabilityDiskFull` | на `/var/tempo` < 10% свободно | `df -h` на хосте и `docker system df -v`; размер volume `chessclass_prod_tempo`; освободить место или уменьшить retention Tempo (§10.8, §10.12); не удалять volume без разбора |
| `ChessClassEmailOutboxStuck` | самое старое недоставленное письмо ждёт > 1 часа | проверить cron `email_outbox_deliver` и логи `worker`; SMTP/egress и `chessclass_email_outbox_pending_total`; разбор и ручной requeue — §10.13 |
| `ChessClassRetentionArchiveStale` | последний gzip-архив retention старше 8 дней | проверить `chessclass_retention_archive_age_seconds`, `retention/status` и логи `worker`; `/srv/archive` и cron `retention_run`; §10.13 |
| `ChessClassBackupFailed` | успешный offsite-бэкап старше 25 часов | проверить cron/скрипт `backup-offsite.ps1`, S3/credentials, ключ шифрования; §17 |
| `ChessClassBackupRestoreFailed` | последний restore-test упал | скачать/расшифровать бэкап, повторить `backup-restore-test.ps1`; users/alembic/S3; §17 |

Маршруты Alertmanager: critical повторяется каждый час, warning — раз в
6 часов; `ChessClassApiDown` подавляет остальные алерты `component="api"`,
critical подавляет warning с тем же alertname/component. При настроенном
email оба уровня дополнительно уходят в email (второй receiver, §10.11).

### 10.8. Retention и данные

| Данные | Где | По умолчанию | Как менять |
|---|---|---|---|
| Traces (Tempo) | volume `chessclass_prod_tempo:/var/tempo` | 168 часов (7 дней), `block_retention` | правка prod-конфига Tempo в репозитории → `up -d --force-recreate tempo` |
| Metrics (Prometheus) | volume `chessclass_prod_prometheus:/prometheus` | 15 дней (`--storage.tsdb.retention.time`) | правка prod-конфига/команды Prometheus → `up -d --force-recreate prometheus` |
| Silences/история Alertmanager | volume `chessclass_prod_alertmanager:/alertmanager` | 120 часов (`--data.retention`) | правка prod-конфига Alertmanager → `up -d --force-recreate alertmanager` |

- Старые блоки Tempo удаляет компактор при следующем цикле; Prometheus
  удаляет блоки старше retention сам. Уменьшение retention сокращает данные,
  доступные для постмортема, — не сокращать до разбора инцидента.
- Место проверять до увеличения retention: traces объёмнее метрик.
- Свободное место на volume traces контролирует `node-exporter`; при остатке
  < 10% срабатывает `ChessClassObservabilityDiskFull` (§10.7, §10.12).
- Конфиги монтируются в контейнеры из репозитория (read-only): правка файла
  внутри контейнера или на сервере мимо репозитория не переживёт пересоздание
  и расходится с git.

### 10.9. Безопасность профиля

- **Grafana не публикуется наружу**: только `https://<host>/grafana/` через
  `edge` (VPN/доверенная сеть) и loopback-порт для отладки; анонимный доступ
  и регистрация выключены. Пароль администратора обязателен
  (`GRAFANA_ADMIN_PASSWORD`), дефолтной пары admin/admin нет.
- **Prometheus и Alertmanager** — только loopback (`127.0.0.1`), наружу не
  публиковать; удалённый доступ — SSH-туннель.
- **Tempo** портов не публикует; связка collector ↔ Tempo — mTLS, клиентский
  сертификат из `deploy/internal-certs/`.
- **Токен бота и chat_id** — только в prod-env; не логировать, не вставлять в
  чаты/тикеты/скриншоты. Рендер конфига с токеном живёт внутри контейнера;
  готовый конфиг с секретом не сохранять в репозиторий и бэкапы. Логи
  Alertmanager проходят маскировку (§10.10), но остаются чувствительными. При
  утечке — перевыпустить токен у BotFather, обновить `.env`, пересоздать
  `alertmanager`.
- **METRICS_TOKEN** — общий секрет api ↔ Prometheus; менять одновременно в
  `.env`, затем пересоздать `api` и `prometheus`.
- **Внутренний CA** (`deploy/internal-certs/`) и prod-env исключены из git
  (проверка — §10.2, п. 3); ротация CA — §7.1 (перевыпуск, пересоздание
  `tempo`/`otel-collector`, проверка mTLS, откат). Ежедневный контроль срока —
  `.\scripts\check-cert-expiry.ps1`.
- Не отключать Alertmanager и не править правила «чтобы убрать шум»: только
  silence с комментарием и TTL, с записью в журнал инцидента
  (`docs/incident-response.md` §4.1).

### 10.10. Маскировка секретов в логах

Alertmanager 0.28 не умеет log-фильтры, а при ошибке Telegram-доставки его
библиотека печатает URL `https://api.telegram.org/bot<TOKEN>/sendMessage`.
Поэтому entrypoint запускает Alertmanager с фильтром
`deploy/observability/prod/redact-logs.awk`:

- `bot<digits>:<token>` → `bot<REDACTED>`;
- `Authorization: Bearer <token>` → `Authorization: Bearer <REDACTED>`.

Фильтр работает построчно (`fflush`), поэтому `docker logs` не задерживает
строки. Проверка после тестового алерта с ошибкой доставки:

```bash
docker compose --env-file .env -f docker-compose.prod.yml --profile observability \
  logs --tail=200 alertmanager | grep -E 'bot[0-9]+:' && echo LEAK || echo masked
```

Команда должна печатать `masked`. Строка `bot<REDACTED>` — нормальный признак
сработавшей маскировки. **TTL:** логи Alertmanager хранить не дольше 14 дней;
compose ограничивает json-file (`max-size=10m`, `max-file=5`), в внешний
SIEM/архив логи выгружать только после маскировки. Ограничение: шаблоны
узкие — URL-encoded или иной формат токена может не совпасть, поэтому логи в
любом случае считать чувствительными и не публиковать. При подозрении на
утечку — перевыпустить токен, пересоздать `alertmanager`, зафиксировать
инцидент (`docs/incident-response.md` §4.1).

### 10.11. Второй receiver: email

Второй канал включается, когда в `.env` одновременно заданы `SMTP_HOST` (из
§5, STARTTLS-порт 587) и `ALERT_EMAIL_TO`. Тогда `alertmanager-render.sh`
оставляет в конфиге receiver `email` и маршруты:

- `critical` → `telegram-critical`, затем `email` (повтор 1 ч);
- `warning` → `telegram`, затем `email` (повтор 6 ч).

Это отдельные маршруты с `continue: true`, а не несколько integrations в одном
receiver: у каждого receiver свой retry, поэтому недоступность SMTP не
задерживает Telegram и наоборот. Если `SMTP_HOST`/`ALERT_EMAIL_TO` не заданы,
email-блоки удаляются при рендере — профиль работает как раньше (только
Telegram). Проверка маршрута — §10.6, п. 4. Alertmanager не поддерживает
implicit TLS (465): для 465 используйте отдельный relay/порт 587.

### 10.12. Диск observability

`node-exporter` (профиль `observability`) монтирует volumes профиля
read-only, поэтому видит их как mountpoint'ы `/var/tempo`, `/prometheus`,
`/alertmanager`, `/var/lib/grafana`. Правило:

```promql
(node_filesystem_avail_bytes{mountpoint="/var/tempo"}
 / node_filesystem_size_bytes{mountpoint="/var/tempo"}) < 0.10
```

— алерт `ChessClassObservabilityDiskFull` (critical, `for: 10m`). Первые шаги:
`df -h` на хосте, `docker system df -v`, размер `chessclass_prod_tempo`;
освободить место или уменьшить retention Tempo (§10.8), не удаляя volume.
Если алерт не приходит, проверить target `node-exporter` в Prometheus
(`/targets`, `up`) и что volume смонтирован в контейнер
(`docker inspect chessclass-prod-node-exporter`).

### 10.13. Stuck email_outbox и stale retention-архив (S-88)

Метрики (S-88) отдаёт `/metrics` api и scrape'ит Prometheus:

| Метрика | Смысл |
|---|---|
| `chessclass_email_outbox_pending_total` | pending + `failed`, исчерпавшие `EMAIL_OUTBOX_MAX_ATTEMPTS` (припаркованы и сами не повторятся) |
| `chessclass_email_outbox_oldest_pending_age_seconds` | возраст самого старого недоставленного письма (pending или retryable failed) |
| `chessclass_retention_archive_age_seconds` | возраст последнего `*.jsonl.gz` в `RETENTION_ARCHIVE_DIR`; 0 — архивов ещё нет |
| `chessclass_failed_jobs` | DLQ (существующие алерты `ChessClassDLQGrowth*`) |

Быстрая проверка значений:

```bash
curl -s 'http://127.0.0.1:9092/api/v1/query?query=chessclass_email_outbox_pending_total'
curl -s 'http://127.0.0.1:9092/api/v1/query?query=chessclass_email_outbox_oldest_pending_age_seconds'
curl -s 'http://127.0.0.1:9092/api/v1/query?query=chessclass_retention_archive_age_seconds'
```

**`ChessClassEmailOutboxStuck` (oldest > 1 ч).**

1. Worker и cron: `docker compose --env-file .env -f docker-compose.prod.yml
   logs --tail=200 worker` — искать `email_outbox_deliver`, `parked`,
   `attempt ... failed`. Cron идёт каждую минуту; если строк нет — проверить,
   что worker запущен и `email_outbox_deliver` есть в его cron-списке.
2. SMTP/egress: `SMTP_HOST/PORT/USER/PASSWORD`, доступность провайдера и
   STARTTLS (587; implicit TLS 465 не поддерживается) — §5, §10.6.
3. Состояние очереди (пользователь/БД из `POSTGRES_USER`/`POSTGRES_DB`; в
   примере — `chess`/`chessclass`):

   ```bash
   docker compose --env-file .env -f docker-compose.prod.yml exec db \
     psql -U chess -d chessclass -c \
     "SELECT status, count(*), min(created_at), max(attempts) FROM email_outbox GROUP BY status;"
   ```

   `last_error` конкретной строки — `SELECT id, attempts, last_error FROM
   email_outbox WHERE status <> 'sent' ORDER BY created_at LIMIT 20;`.
   Не удаляйте pending-строки: в теле письма одноразовая ссылка согласия.
4. После устранения причины вернуть конкретную припаркованную строку в
   очередь (точечно, не массово):

   ```bash
   docker compose --env-file .env -f docker-compose.prod.yml exec db \
     psql -U chess -d chessclass -c \
     "UPDATE email_outbox SET status='pending', attempts=0, next_attempt_at=now() WHERE id=<id>;"
   ```

   Следующий cron-тик отправит письмо; проверить `status='sent'` и
   `sent_at`.

**`ChessClassRetentionArchiveStale` (age > 8 дней).**

1. `GET /admin/observability/retention/status` — `rows` по политикам и
   `lastRun`. Если строк под retention нет, архив не создаётся by design:
   age растёт, хотя cron работает. Сначала убедиться, что есть данные старше
   cutoff.
2. Логи `worker` (`retention_run`), диск и права `RETENTION_ARCHIVE_DIR`
   (`/srv/archive` в prod, volume `chessclass_archive`): каталог должен быть
   записываемым для api/worker.
3. Ручной прогон — §8: сначала `POST /admin/observability/retention/run`
   с `{"dryRun": true}`, затем без dry-run. После успешного прогона метрика
   `chessclass_retention_archive_age_seconds` должна упасть до нескольких
   минут (при наличии строк).
4. Не удалять старые архивы и volume без разбора: архивы могут содержать PII
   (audit/email_outbox); хранить по политике и не выгружать в общий SIEM.

## 11. Защита от DoS и rate-limit (S-90)

Два независимых слоя:

| Слой | Что ограничивает | Значение |
|---|---|---|
| edge nginx | `/api/v1/auth/*` по IP | 10 req/min, burst 9 → 11-й 429 |
| edge nginx | `/api/*` по IP | 60 req/min, burst 30 |
| API | неудачные логины на аккаунт (email) | 5/мин → lockout 10 мин |
| API | неудачные логины с IP (soft) | 50/мин → пауза 1 мин |

- nginx возвращает **429** (`limit_req_status 429`), а не 503. Проверка
  конфига и семантики без prod-стенда:

  ```powershell
  .\scripts\edge-ratelimit-smoke.ps1
  ```

  Ожидаемо: `auth: 10x200, 11th=429`.
- Логи edge при срабатывании: `docker compose --env-file .env -f
  docker-compose.prod.yml logs --tail=200 edge` — строка `limiting requests`.
- **Реальный IP.** Edge передаёт `X-Forwarded-For`/`X-Real-IP`; API доверяет
  им только от `PROXY_TRUSTED_HOSTS` (IP/CIDR edge; в prod/staging —
  `172.16.0.0/12,127.0.0.1`). Если задано `*`, API доверяет заголовкам от
  любого источника — допустимо только при закрытом снаружи порту API.
  Проверка: в логах/аудите IP клиента, а не `172.x` edge; тест —
  `tests/test_edge_auth_s90.py`.
- **Per-account lockout.** Ключи Redis: `lockout:account:{email}` (10 мин),
  `lockout:ip:{ip}` (1 мин), счётчики `lockout:fail:*`. Разблокировать
  конкретный аккаунт при ложном срабатывании:

  ```bash
  docker compose --env-file .env -f docker-compose.prod.yml exec redis \
    redis-cli DEL "lockout:account:user@example.com"
  ```

  Не удалять `lockout:*` массово без разбора инцидента: это снимет защиту.
- **NAT и общий IP.** За школьным NAT все пользователи могут выглядеть одним
  IP; edge-лимиты 10/60 req/min на IP могут блокировать класс. При массовых
  429 легитимным пользователям: проверить `limiting requests`, временно
  увеличить `burst`/`rate` в `deploy/nginx/edge.conf` через репозиторий и
  пересоздать `edge`; не отключать лимиты полностью. Альтернатива на будущее —
  лимит по `Authorization`/session на API, а не только по IP.
- **JWT legacy.** В prod/staging `JWT_LEGACY_HS256=false` и
  `JWT_ALGORITHM=RS256`; после ротации ключей (§9) старые HS256-токены
  перестают приниматься. Startup-warning `JWT_LEGACY_HS256=true` — сигнал
  завершить миграцию.

## 12. Разбор 403 / объектная авторизация (S-91)

`{id}`-эндпоинты проверяют владение объектом (`backend/core/authz.py`):
**404** — объекта нет, **403** — объект существует, но принадлежит другому
ученику/учителю. Это не сбой RBAC-роли: admin/auditor-scope может видеть
объект, а teacher — только учеников своих классов.

Порядок разбора:

1. **Кто запрашивает.** `sub`/`role` access-JWT; для teacher — его `user_id`,
   для auditor — `auditor_scope` из `user_profiles.prefs`.
2. **Владение объектом.**
   - PDF: `reports_pdfs.student_id`/`requested_by`;
   - бот/партия/сдача: `user_id` владельца;
   - класс/ученик: `classes.teacher_id` + `class_members`;
   - PvP: `pvp_rooms.host_user_id`/`guest_user_id`.
3. **Класс ученика.** Если teacher должен видеть ученика, но не видит —
   проверить членство (добавить в класс, а не ослаблять authz):

   ```bash
   docker compose --env-file .env -f docker-compose.prod.yml exec db \
     psql -U chess -d chessclass -c \
     "SELECT c.id, c.name, c.teacher_id FROM classes c \
      JOIN class_members m ON m.class_id = c.id \
      WHERE m.user_id = <student_id>;"
   ```

4. **Auditor scope.** Отсутствующий/`false` scope — fail-closed 403.
   Проверить/выдать admin'ом:

   ```bash
   curl -s -X PATCH https://<host>/api/v1/admin/users/<auditor_id>/auditor-scope \
     -H "Authorization: Bearer <admin-jwt>" -H "Content-Type: application/json" \
     -d '{"scopes":{"audit":true,"reports":true,"flags":true}}'
   ```

5. **Аудит учителя.** Teacher видит только `actor_id == self`; не искать
   чужие действия через `actorId` — фильтр принудительно сужается. Полный
   журнал — admin или auditor scope `audit`.
6. **Не обходить 403** правкой кода/выдачей admin. Если доступ нужен
   легитимно: добавить ученика в класс, выдать auditor scope, либо
   зафиксировать инцидент. 403 на чужой объект — ожидаемое поведение BOLA-
   защиты; 5xx/500 при этом — баг, эскалировать.

## 13. Деплой из GHCR и rollback (S-92)

Prod тянет готовые образы `ghcr.io/iilmchat/chessclass-backend` и
`ghcr.io/iilmchat/chessclass-frontend`; локальной сборки в prod-compose нет.
Публикация — job `publish` в `.github/workflows/ci.yml` после зелёных
backend/frontend/e2e/secrets; теги — `<sha>` и `<ref>` (`main` или `vX.Y.Z`).

1. **Подготовка сервера.** Для приватного пакета — вход с токеном
   `read:packages` (не логировать токен):

   ```bash
   echo "$GHCR_TOKEN" | docker login ghcr.io -u <github-user> --password-stdin
   ```

2. **Деплой версии.** `IMAGE_TAG` — релизный тег (`v0.8.0`) или sha:

   ```bash
   cd /opt/chessclass
   git fetch --tags
   IMAGE_TAG=v0.8.0 docker compose --env-file .env -f docker-compose.prod.yml pull
   IMAGE_TAG=v0.8.0 docker compose --env-file .env -f docker-compose.prod.yml up -d
   docker compose --env-file .env -f docker-compose.prod.yml ps
   curl -fsS http://127.0.0.1:8020/readyz
   ```

3. **Rollback** — смена `IMAGE_TAG` на предыдущий опубликованный тег и
   повторный `pull`/`up -d`:

   ```bash
   IMAGE_TAG=v0.7.1 docker compose --env-file .env -f docker-compose.prod.yml pull
   IMAGE_TAG=v0.7.1 docker compose --env-file .env -f docker-compose.prod.yml up -d
   ```

   Миграции forward-only: если новая версия уже применила несовместимую
   миграцию, откат образа без отката БД может не подняться. Перед релизом
   проверять `alembic upgrade head` на копии; откат схемы — только по
   отдельному плану/бэкапу.

4. **Проверка после деплоя:** `/healthz`, `/readyz`, `/metrics`,
   `scripts/observability-selftest.ps1 -Stack` (или smoke), e2e на staging.
   Образы неизменяемы: не пересобирать тег на сервере.

## 14. Диагностика ошибок через Sentry (S-92)

- Включается только при непустом `SENTRY_DSN`; `SENTRY_ENVIRONMENT`
  (`prod`/`staging`), `SENTRY_TRACES_SAMPLE_RATE=0.1`. Пусто — SDK не
  инициализируется, приложение работает как раньше.
- Frontend: `VITE_SENTRY_DSN` передаётся build-arg при публикации
  (`publish` workflow); без него Sentry в SPA выключен.
- **Trace-id:** API пишет `trace_id` в JSON-логи; Sentry хранит его в
  `contexts.trace.trace_id`. В Search — `trace:<32-hex>` или фильтр по
  `environment:prod`. Сопоставлять с Tempo/Grafana по тому же id.
- **PII:** `send_default_pii=False`, тела запросов не отправляются
  (`max_request_body_size="never"`), DSN не логируется. Email/токены всё
  равно не вставлять в `extra`/`tags`; при подозрении на утечку — удалить
  событие и перевыпустить затронутые секреты.
- DSN хранится только в env/секретах GitHub; в `.env.example` — пустой
  плейсхолдер. Проверка старта с фиктивным DSN — `tests/test_error_tracking.py`.

## 15. Ротация логов (S-92)

- `api`, `worker` и `worker-match-*` в prod-compose используют Docker
  `json-file` с `max-size=10m`, `max-file=5` (≈50 MB на контейнер). Проверка:

  ```bash
  docker inspect --format '{{json .HostConfig.LogConfig}}' chessclass-prod-api
  docker compose --env-file .env -f docker-compose.prod.yml logs --tail=200 api
  ```

- Если uvicorn/arq пишут в файл вне Docker (нештатный запуск), установить
  `deploy/logrotate/chessclass` в `/etc/logrotate.d/chessclass`:

  ```bash
  sudo cp deploy/logrotate/chessclass /etc/logrotate.d/chessclass
  sudo logrotate -d /etc/logrotate.d/chessclass   # dry-run
  ```

  Политика: daily, 14 файлов, gzip, `copytruncate`. Логи Alertmanager —
  отдельно, TTL 14 дней (§10.10).
- Диск: `ChessClassObservabilityDiskFull` (<10% на `/var/tempo`) не покрывает
  раздел с Docker-логами; следить за `docker system df` и свободным местом
  хоста. Не делать `docker system prune -a` без подтверждения (KI-001).

## 16. Метрики при нескольких uvicorn-воркерах (S-92)

- В prod `api` задан `PROMETHEUS_MULTIPROC_DIR=/tmp/prom_multiproc`;
  `core/http_metrics.py` использует `prometheus_client.multiprocess`: каждый
  воркер пишет свои серии, `/metrics` собирает `MultiProcessCollector`.
  Без этой переменной (dev/CI) работает обычный process-local registry.
- Проверка агрегации:

  ```powershell
  .\scripts\multiprocess-metrics-smoke.ps1
  ```

  Ожидаемо: 2 uvicorn-воркера, `healthz`-запросы видны в агрегированном
  `/metrics` (>= отправленных).
- Каталог — временный (`/tmp`): при рестарте контейнера счётчики начинаются
  с нуля; Prometheus `rate`/`increase` корректно переживает reset. Не
  монтировать один и тот же каталог между разными контейнерами.
- Если `/metrics` отдаёт 500 — проверить, что каталог существует и writable
  для `api`, версия `prometheus-client` совпадает с lock; `mark_process_dead`
  вызывается в lifespan при остановке воркера.
- Прочие gauges (`db_up`, очереди, outbox/retention) остаются per-process,
  но отражают общее состояние БД; для p95/error-rate агрегируются именно
  HTTP RED-метрики.

## 17. Offsite-бэкапы S3 (S-93)

Настройка в prod/staging `.env`:

```dotenv
BACKUP_S3_ENDPOINT=          # пусто для AWS; https://storage.yandexcloud.net / MinIO
BACKUP_S3_BUCKET=CHANGE_ME
BACKUP_S3_PREFIX=postgres
BACKUP_S3_ACCESS_KEY=CHANGE_ME
BACKUP_S3_SECRET_KEY=CHANGE_ME
BACKUP_ENCRYPTION_KEY=       # ровно 32 hex-символа, только в секретах
BACKUP_STATUS_VOLUME=chessclass_prod_archive
BACKUP_DOCKER_NETWORK=chessclass-prod-net
BACKUP_EXPECTED_ALEMBIC=0035_s83_email_outbox
```

- **Запуск** (вручную или cron/Task Scheduler ежедневно):

  ```powershell
  .\scripts\backup-offsite.ps1 -Container chessclass-prod-db
  ```

  Скрипт делает `pg_dump -Fc`, шифрует `openssl enc -aes-256-cbc -pbkdf2`,
  загружает в S3 (host `aws`/`mc` или docker `amazon/aws-cli`) и пишет JSON
  `size/sha256/duration/s3_path`. `BACKUP_ENCRYPTION_KEY` не логируется;
  локальный файл удаляется, если не `-KeepLocal`.
- **Retention:** lifecycle policy на bucket — 30 дней (например, S3 Lifecycle
  `Expiration: 30`); локальный `BACKUP_DIR` — 14 дней (`backup.ps1`).
- **Пути (v0.8.1):** `-BackupDir` и `-BackupFile` всегда резолвятся в
  абсолютный путь перед `docker -v`. На Windows относительный путь ломал
  bind mount (Docker создавал named volume) — исправлено в v0.8.1.
  `backup-offsite.ps1 -DryRun` показывает итоговый `docker_mount` без
  выполнения; smoke — `scripts/backup-relative-dir-smoke.ps1`.
- **Restore-test** (weekly и после релиза):

  ```powershell
  .\scripts\backup-restore-test.ps1 -RestorePort 5439
  ```

  Скрипт скачивает последний `*.dump.enc`, расшифровывает, поднимает
  временный `chessclass-restore-test` на 5439, восстанавливает и проверяет
  `users > 0` + `alembic_version`. Контейнер/файлы удаляются в `finally`.
- **Метрики:** `chessclass_backup_last_success_timestamp_seconds`,
  `chessclass_backup_restore_ok` (1/0). Алерты:
  `ChessClassBackupFailed` (>25 ч без успеха, critical) и
  `ChessClassBackupRestoreFailed` (`restore_ok=0`, critical).
- **Если алерт сработал:** проверить cron/Task Scheduler, `aws s3 ls`,
  `BACKUP_S3_*`, `BACKUP_ENCRYPTION_KEY`, свободное место; выполнить
  `backup-offsite.ps1` вручную, затем `backup-restore-test.ps1`. Не удалять
  старые архивы до успешного restore.
- **Ограничения:** dump содержит PII; архив шифруется, но ключ — критический
  секрет. При утечке ключа — перевыпустить ключ, перешифровать/удалить
  затронутые объекты и зафиксировать инцидент.

## 18. SMTP-диагностика (S-93)

- Проверка конфигурации: `SMTP_HOST/PORT` (587 + `SMTP_STARTTLS=true` или
  465 + `SMTP_SSL=true`), `SMTP_USER/PASSWORD`, `SMTP_FROM`; пустой
  `SMTP_HOST` — dev-консоль, в prod это ошибка.
- **Smoke без боевого провайдера:**

  ```powershell
  .\scripts\smtp-smoke.ps1
  ```

  Поднимает `observability-smtp-sink.py` в Docker, отправляет verification и
  password-reset, проверяет получение. STARTTLS/SSL-ветки проверяются
  `backend/tests/test_email.py` (fake SMTP).
- **Email outbox:** `/ops`/`email_outbox`; SQL:

  ```bash
  docker compose --env-file .env -f docker-compose.prod.yml exec db \
    psql -U chess -d chessclass -c \
    "SELECT status, count(*), min(created_at), max(attempts) FROM email_outbox GROUP BY status;"
  ```

  `failed` с `attempts >= EMAIL_OUTBOX_MAX_ATTEMPTS` — parked; смотреть
  `last_error`, чинить SMTP и возвращать строку точечно (§10.13).
- **5xx/4xx от провайдера:** `logs worker` по `email_outbox`; проверить
  квоты, authentication, From-domain/SPF/DKIM, STARTTLS-порт. 535 —
  неверный пароль/логин; 550 — политика получателя; 421/451 — временный
  отказ (retry сам). Bounce приходит на `SMTP_FROM`/return-path — настроить
  ящик и разбирать вручную; не удалять failed-строки без анализа.
- Верификация email обязательна: без SMTP новые пользователи не смогут
  войти; `SMTP_HOST` должен быть задан до публичного запуска. Release-notes
  v0.8.0 фиксируют это требование для оператора.

## 19. Сетевая изоляция песочницы (S-97)

По умолчанию `SANDBOX_NETWORK_ISOLATION=true`,
`SANDBOX_NETWORK_BACKEND=auto`: `bwrap --unshare-net` (uid 1000, без
`--privileged`/CAP_SYS_ADMIN) → `unshare -n` (если root) → запуск без сети
с `network_isolation_enforced=false` и warning в `limits_warning`.

- **Проверка bwrap в контейнере:**

  ```bash
  docker compose --env-file .env -f docker-compose.prod.yml exec -T api \
    sh -c "bwrap --unshare-net --dev /dev --proc /proc \
      --ro-bind /usr /usr --ro-bind /usr/local /usr/local \
      --ro-bind /lib /lib --ro-bind /lib64 /lib64 \
      --tmpfs /tmp --chdir /tmp --die-with-parent \
      python -c 'print(\"bwrap-ok\")'"
  ```

- **Проверка, что сеть реально закрыта:**

  ```bash
  docker compose --env-file .env -f docker-compose.prod.yml exec -T api \
    sh -c "bwrap --unshare-net --dev /dev --proc /proc \
      --ro-bind /usr /usr --ro-bind /usr/local /usr/local \
      --ro-bind /lib /lib --ro-bind /lib64 /lib64 \
      --tmpfs /tmp --chdir /tmp --die-with-parent \
      python -c \"import socket; s=socket.socket(); s.settimeout(1); \
        s.connect(('127.0.0.1', 6379))\""
  ```

  Ожидаемо `ConnectionRefusedError`/`OSError` (в netns нет Redis).
- **Результат executor:** `network_isolation_enforced=true`,
  `network_backend=bwrap`; при fallback — `false`/`none` и
  `limits_warning`. Проверка из API-контейнера:

  ```bash
  docker compose --env-file .env -f docker-compose.prod.yml exec -T api \
    python -c "from sandbox.executor import run_sync; \
      r=run_sync('print(1)'); print(r['network_isolation_enforced'], r['network_backend'])"
  ```

- **`bwrap: setting up uid map: Permission denied` / `No permissions to
  create a new namespace`.** Не включены unprivileged user namespaces или
  не применён seccomp-профиль. Проверить:
  `sysctl kernel.unprivileged_userns_clone` (если есть) и
  `sysctl user.max_user_namespaces` (>0); в Docker — что сервис использует
  `security_opt: ["seccomp=./deploy/seccomp-sandbox.json"]` (профиль
  добавляет `unshare`/`clone`/mount-syscalls к Docker default, без
  `seccomp=unconfined`). На хосте при необходимости:
  `sysctl -w kernel.unprivileged_userns_clone=1` (где доступно).
- **Fallback.** Если bwrap недоступен/не может создать namespace, executor
  повторяет запуск через `unshare -n` (root) или без сети; задание не
  падает, но `network_isolation_enforced=false` и warning. Для строгого
  режима задайте `SANDBOX_NETWORK_BACKEND=bwrap` — тогда без bwrap
  изоляция не подтверждается (warning остаётся).
- **`deploy/seccomp-sandbox.json`** — копия Docker default seccomp с
  дополнительными namespace/mount syscalls для bwrap. Обновлять при
  обновлении Docker/ядра; не заменять на `seccomp=unconfined`.
- **Тесты:** `tests/sandbox/test_attacks.py` — bwrap probe, попытка
  `127.0.0.1:6379`, fallback/warning, `network_isolation_enforced`.

## 20. Legal Hold и DSAR (S-98)

**Legal hold** блокирует retention и DSAR для субъекта. Создавать только по
письменному запросу юриста/школы; `reason` — без лишних PII.

```bash
# создать hold на пользователя (admin JWT)
curl -X POST "$API/admin/legal-holds" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"subjectType":"user","subjectId":"123","reason":"litigation-2026-11"}'

# список активных / всех
curl "$API/admin/legal-holds?includeRevoked=false" -H "Authorization: Bearer $ADMIN_TOKEN"
curl "$API/admin/legal-holds?includeRevoked=true"  -H "Authorization: Bearer $ADMIN_TOKEN"

# отозвать
curl -X DELETE "$API/admin/legal-holds/42" -H "Authorization: Bearer $ADMIN_TOKEN"
```

- Активный hold: `revoked_at IS NULL` и `expires_at` пуст/в будущем.
- Retention пропускает `email_outbox` субъекта (body и metadata) и пишет
  `retention.skipped_legal_hold` в `audit_logs`; DSAR erase при hold
  возвращает **409 `legal_hold_active`**.
- `legal_holds` не удаляются при erase (история удержания); после отзыва
  hold DSAR можно повторить.

**DSAR erase** (admin, только после подтверждения личности/запроса):

```bash
curl -X POST "$API/admin/users/123/erase" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"reason":"GDPR/152-ФЗ request 2026-11-12"}'
```

Что происходит: `users.email=deleted-{id}@anon`, случайный пароль,
`is_active=false`; профиль/prefs обезличиваются; удаляются
`email_outbox` (по старому email), `email_tokens`, `refresh_sessions`,
`telegram_links`, `telegram_outbox`, `review_cards`, `pvp_ratings`;
`bot_versions.code`, `py_submissions.code`, `chess_games.pgn` →
`# erased`; `parental_consents.parent_email` → `deleted-{id}@anon`.
`audit_logs`, `llm_calls`, `legal_holds` остаются.

- При 409: проверить `GET /admin/legal-holds`; отозвать hold только после
  юридического согласования, затем повторить erase.
- Проверка audit:

  ```sql
  SELECT action, target_id, meta, created_at
  FROM audit_logs
  WHERE action IN ('user.erased','legal_hold.create','legal_hold.revoke',
                   'retention.skipped_legal_hold')
  ORDER BY created_at DESC LIMIT 20;
  ```

- Retention `email_outbox`: body чистится через
  `EMAIL_OUTBOX_BODY_RETENTION_DAYS=30` (`[deleted]`), метаданные
  удаляются через `EMAIL_OUTBOX_RETENTION_DAYS=90`; архив
  `email_outbox-*.jsonl.gz` не содержит body. Метрики:
  `chessclass_legal_holds_active_total`,
  `chessclass_email_outbox_body_pending_scrub_total`,
  `chessclass_retention_last_success_timestamp_seconds`.
