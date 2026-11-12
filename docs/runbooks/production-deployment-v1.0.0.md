# Runbook: production-деплой ChessClass v1.0.0

**Версия:** v1.0.0 · **Дата:** 2026-11-12 · **Стенд:** Linux (Ubuntu 24.04+),
Docker 29+, Compose v2 · **Тип:** first deploy + обновление

Документ описывает развёртывание production-контура из GHCR-образов.
Источник истины по эксплуатации — [operations.md](operations.md); здесь —
линейный сценарий первого запуска и проверки.

> ⚠️ **Известный блокер на момент приёмки:** образы опубликованы с тегом
> `v1.0.0`, а compose и `.env.prod.example` по умолчанию используют
> `IMAGE_TAG=1.0.0`. Тег `1.0.0` в GHCR отсутствует, `docker compose pull`
> упадёт с `manifest unknown`. В шаге 2 обязательно выставьте
> `IMAGE_TAG=v1.0.0`.

## 0. Предусловия

| Параметр | Минимум | Рекомендуется |
|---|---|---|
| CPU | 4 vCPU | 8 vCPU (Stockfish + 5 worker'ов) |
| RAM | 8 ГБ | 16 ГБ |
| Диск | 40 ГБ SSD | 80 ГБ SSD |
| ОС | Ubuntu 24.04 | Ubuntu 24.04 LTS |
| Docker | 29.x + Compose v2 | 29.x |
| Сеть | 80/443 открыты наружу, 22 — с админских IP | + UFW/fail2ban |

Проверить до начала:

- [ ] DNS: `A` записи домена (и `www`, если нужен) указывают на IP сервера,
      TTL уже истёк (`dig +short <domain>`).
- [ ] Нет занятых портов 80/443 (`ss -ltnp | grep -E ':80|:443'`).
- [ ] Есть доступ к GHCR (пакеты `chessclass-backend/frontend` приватные —
      `docker login ghcr.io` под аккаунтом с `read:packages`).
- [ ] Часы синхронизированы (`timedatectl`), зона MSK.
- [ ] Swap ≥ 2 ГБ при 8 ГБ RAM.

Ресурсы под стек (ориентир, лимиты в compose пока не заданы — см. отчёт
аудита): api 1.5–2 ГБ, db 1–2 ГБ, redis 256 МБ, 5 worker'ов по 256–512 МБ,
edge/web/caddy по 128 МБ, observability 1–1.5 ГБ при включённом профиле.

## 1. Получить код и тег

```bash
git clone https://github.com/iilmchat/ai_chessclass.git /opt/chessclass
cd /opt/chessclass
git fetch --tags
git checkout v1.0.0
git describe --tags --exact-match      # → v1.0.0
```

Рабочее дерево должно быть чистым: `git status --short` пуст.

## 2. Подготовить окружение

**Важно:** сервисы читают env через `env_file: ${ENV_FILE:-.env}`. Файл
`.env.prod` сам по себе контейнерам не виден — `--env-file .env.prod` влияет
только на подстановку переменных в compose. Поэтому:

```bash
cp .env.prod.example .env
chmod 600 .env
```

(альтернатива: оставить `.env.prod` и всегда запускать compose с
`ENV_FILE=.env.prod`; тогда переменные попадут и в контейнеры).

Обязательно заполнить:

| Переменная | Комментарий |
|---|---|
| `IMAGE_TAG` | **`v1.0.0`** (не `1.0.0` — см. блокер выше) |
| `POSTGRES_PASSWORD` | 32+ символа, только из менеджера секретов |
| `JWT_SECRET` | 64 случайных символа (даже при RS256 обязателен) |
| `JWT_ALGORITHM`, `JWT_LEGACY_HS256` | `RS256`, `false` |
| `JWT_KID` | например `prod-2026-11` |
| `JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH` | `/srv/jwt/private.pem`, `/srv/jwt/public.pem` |
| `SMTP_HOST/USER/PASSWORD/FROM` | боевой ящик; `SMTP_FROM` — домен из SPF/DKIM |
| `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_SSL` | 587+STARTTLS или 465+SSL |
| `BACKUP_S3_ENDPOINT/BUCKET/PREFIX` | S3/MinIO, отдельный префикс `postgres-prod` |
| `BACKUP_S3_ACCESS_KEY/SECRET_KEY` | ключ с правами на бакет |
| `BACKUP_ENCRYPTION_KEY` | ровно 32 hex-символа |
| `BACKUP_EXPECTED_ALEMBIC` | `0036_s98_legal_hold` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALERT_CHAT_ID` | обязательны при `--profile observability`, иначе Alertmanager не стартует |
| `GRAFANA_ADMIN_PASSWORD` | не `CHANGE_ME` |
| `METRICS_TOKEN` | рекомендуется задать (иначе `/metrics` без токена) |
| `SENTRY_DSN` | опционально; пусто — error-tracking выключен |
| `WEB_BASE_URL` | `https://<domain>` |
| `PROXY_TRUSTED_HOSTS` | `172.16.0.0/12,127.0.0.1` |
| `WEB_PORT` | `127.0.0.1:3200` — так web не торчит наружу (см. §5) |

`SEED_*` менять не нужно и **запускать seed на prod нельзя**: сервис `seed`
создаёт демо-пользователей и включён только в профиль `tools`.

Проверка синтаксиса без секретов:

```bash
docker compose -f docker-compose.prod.yml --env-file .env config -q && echo OK
```

## 3. RS256-ключи

```powershell
# Windows-админстанция, из корня репозитория:
.\scripts\gen-jwt-keys.ps1 -Force
```

или на сервере:

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out deploy/jwt/private.pem
openssl rsa -pubout -in deploy/jwt/private.pem -out deploy/jwt/public.pem
chmod 644 deploy/jwt/private.pem deploy/jwt/public.pem
```

Права `0644` обязательны: api работает под `appuser` (uid 1000) и иначе
падает на логине с `PermissionError: /srv/jwt/private.pem` → HTTP 500.

```bash
ls -l deploy/jwt/    # private.pem/public.pem, 644, не в git
```

## 4. TLS-сертификаты

Для первого запуска и smoke допустим self-signed:

```bash
pwsh scripts/gen-self-signed-cert.ps1 -Force   # или openssl на сервере
```

Боевой вариант — Let's Encrypt по webroot (edge отдаёт
`/.well-known/acme-challenge/` из named-volume `chessclass_prod_certbot`):

```bash
# 1) поднять edge с self-signed, чтобы challenge был доступен
docker compose -f docker-compose.prod.yml --env-file .env up -d edge

# 2) выпустить сертификат
docker run --rm \
  -v chessclass_prod_certbot:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d <domain> --email <admin@domain> --agree-tos --non-interactive

# 3) положить сертификаты в deploy/certs (монтируется в edge :ro)
cp /etc/letsencrypt/live/<domain>/fullchain.pem deploy/certs/fullchain.pem
cp /etc/letsencrypt/live/<domain>/privkey.pem   deploy/certs/privkey.pem
chmod 644 deploy/certs/*.pem

# 4) перечитать конфиг
docker compose -f docker-compose.prod.yml --env-file .env exec edge nginx -s reload
```

Автопродление (обязательно добавить — в репозитории автоматизации нет):

```cron
# /etc/cron.d/chessclass-cert
0 4 * * * root certbot renew --quiet --deploy-hook "docker compose -f /opt/chessclass/docker-compose.prod.yml --env-file /opt/chessclass/.env exec edge nginx -s reload"
```

Контроль: `pwsh scripts/check-cert-expiry.ps1 -Paths deploy/certs/fullchain.pem`
(< 30 дней — warning, < 7 — critical). Алерта на срок в prod пока нет —
добавьте проверку в cron и мониторинг.

## 5. Edge и публикация портов

`deploy/nginx/edge.conf` содержит `server_name _;` — catch-all. Для строгой
проверки Host замените на домен (или оставьте `_`, понимая, что отвечаем на
любой Host).

Наружу должны смотреть только edge (80/443). API уже слушает loopback
(`API_BIND=127.0.0.1`). Web по умолчанию публикуется на `0.0.0.0:3200` —
задайте в `.env`:

```dotenv
WEB_PORT=127.0.0.1:3200
```

Проверка после `up`:

```bash
ss -ltnp | grep -E ':(80|443|8020|3200|9092|9093|3002)\b'
# ожидаем: 80/443 — 0.0.0.0; остальные — 127.0.0.1
```

## 6. Подъём стека

```bash
docker compose -f docker-compose.prod.yml --env-file .env pull
docker compose -f docker-compose.prod.yml --env-file .env up -d migrate
docker compose -f docker-compose.prod.yml --env-file .env ps -a | grep migrate
# migrate должен завершиться с кодом 0

docker compose -f docker-compose.prod.yml --env-file .env up -d
docker compose -f docker-compose.prod.yml --env-file .env ps
```

Ожидаемо: `db`, `redis`, `api`, `web`, `edge`, `worker*` — `healthy`/`running`;
`migrate` — `exited (0)`.

## 7. Проверка API и edge

```bash
curl -fsS https://<domain>/healthz | jq .
curl -fsS https://<domain>/readyz  | jq .
# readyz: status=ready, migrationsUpToDate=true, revision=head=0036_s98_legal_hold

curl -fsS https://<domain>/.well-known/jwks.json | jq '.keys[0].kid'
# kid = JWT_KID

curl -s -o /dev/null -w '%{http_code}\n' http://<domain>/   # 301 → https
```

Smoke (с админстанции):

```powershell
.\scripts\smoke-prod.ps1 -ApiBase https://<domain>/api/v1 `
  -WebBase https://<domain> -EdgeBase https://<domain>
```

## 8. Observability

```bash
# TELEGRAM_BOT_TOKEN и TELEGRAM_ALERT_CHAT_ID должны быть заданы,
# иначе Alertmanager уйдёт в restart-loop с "не задан"
docker compose -f docker-compose.prod.yml --env-file .env \
  --profile observability up -d
```

Проверки:

- [ ] Prometheus `http://127.0.0.1:9092/api/v1/targets` — targets
      `chessclass-api`, `otel-collector`, `node-exporter`, `prometheus`,
      `alertmanager` в состоянии `up`.
- [ ] `http://127.0.0.1:9092/api/v1/rules` — 12 правил `ChessClass*`.
- [ ] Alertmanager `http://127.0.0.1:9093/-/ready` → 200.
- [ ] Grafana `https://<domain>/grafana/` — вход `GRAFANA_ADMIN_USER/PASSWORD`,
      datasources Prometheus/Tempo.
- [ ] Тестовый алерт доходит в Telegram/email и приходит `resolved`
      (operations §10.6).
- [ ] `/admin/observability/alerts` под админом — нет `critical`.

Self-test (с админстанции, статические проверки без боевых ключей):

```powershell
.\scripts\observability-selftest.ps1
```

## 9. Первый offsite-бэкап и restore-дрилл

Скрипт `scripts/backup-offsite.ps1` — PowerShell. На Linux-сервере без
`pwsh` используйте эквивалент:

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker exec chessclass-prod-db pg_dump -U chess -d chessclass -Fc \
  -f /tmp/$STAMP.dump
docker cp chessclass-prod-db:/tmp/$STAMP.dump ./$STAMP.dump
openssl enc -aes-256-cbc -pbkdf2 -salt -in ./$STAMP.dump \
  -out ./$STAMP.dump.enc -pass env:BACKUP_ENCRYPTION_KEY
sha256sum ./$STAMP.dump.enc
```

Загрузка в S3 (host `aws`/`mc` или docker `amazon/aws-cli`):

```bash
aws --endpoint-url "$BACKUP_S3_ENDPOINT" s3 cp ./$STAMP.dump.enc \
  "s3://$BACKUP_S3_BUCKET/postgres-prod/$STAMP.dump.enc"
```

Затем — восстановление в отдельную БД (аналог
`scripts/backup-restore-test.ps1`): поднять temp Postgres, `pg_restore`,
проверить `users > 0` и `alembic_version = 0036_s98_legal_hold`, удалить
temp-контейнер.

Локальный бэкап по расписанию — `deploy/cron/chessclass-backup`
(03:00, retention 14 дней); offsite-автоматизацию для Linux нужно добавить
(в репозитории её нет — см. отчёт аудита).

## 10. Итоговая приёмка

```powershell
.\scripts\staging-acceptance.ps1 `
  -BaseUrl https://<domain>/api/v1 `
  -AdminEmail <admin> -AdminPassword <пароль> `
  -TestStudentEmail accept-YYYY-MM-DD@<домен>
```

Ожидаемо `exit=0`; `email_outbox` — `SKIP` (verify-письмо синхронное).
Проверьте реальный ящик: письмо «Подтвердите email — ChessClass»,
`spf=pass`, `dkim=pass`, `dmarc=pass`.

**Примечание:** `backup_metric` читает `/metrics` с API. Через edge он
недоступен (SPA), поэтому для полной проверки используйте
`-BaseUrl http://127.0.0.1:8020/api/v1` на самом сервере или отдельно
проверьте `curl -H "Authorization: Bearer $METRICS_TOKEN" http://127.0.0.1:8020/metrics`.

## 11. Откат

```bash
# 1) вернуться на предыдущий тег образа
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=v0.9.0/' .env
docker compose -f docker-compose.prod.yml --env-file .env pull
docker compose -f docker-compose.prod.yml --env-file .env up -d

# 2) если новая схема несовместима — восстановить БД из offsite-дампа
```

Миграции **forward-only**: `alembic downgrade` в prod не выполняется и не
тестируется. Откат кода не откатывает схему — при несовместимой миграции
единственный путь — restore из бэкапа (с потерей данных после дампа).

## 12. Пост-деплой

- [ ] `/etc/cron.d/chessclass-backup` установлен, лог пишется.
- [ ] Certbot renew + reload edge в cron.
- [ ] logrotate `deploy/logrotate/chessclass` установлен.
- [ ] UFW: 22 (админские IP), 80, 443; fail2ban на sshd/nginx.
- [ ] Ротация секретов: `.env` 600, ключи 644, доступ только root/deploy.
- [ ] `git status` на сервере: изменён только `.env` и `deploy/certs/*`
      (не коммитить).
