# Отчёт: Staging Acceptance v0.9.0 (операция)

**Дата:** 2026-11-12 · **Тип:** операционная приёмка (не спринт) ·
**Версия:** v0.9.0 (`8d8c7c9`, tag `v0.9.0-2-g8d8c7c9`) · **Статус:** ✅ стенд
принят, GPU подтверждён (57,4 ток/с).
**Артефакты:** `scripts/staging-acceptance.ps1` · `scripts/backup-offsite.ps1` ·
`scripts/backup-restore-test.ps1` · `scripts/observability-selftest.ps1`.
**Runbook:** `docs/runbooks/final-acceptance.md`, `docs/runbooks/staging.md` §4.

## 1. Стенд

- `docker-compose.staging.yml` + `.env.staging` (локально, Docker 29.8.1,
  Compose v2), сеть `chessclass-staging-net`.
- Сервисы: `db` (pgvector/pg17), `redis`, `api`, `worker` + 4 match-worker,
  `web`, `edge` (nginx 1.27, TLS self-signed), профиль `observability`
  (`tempo`, `otel-collector`, `prometheus`, `grafana`).
- Миграции: `0036_s98_legal_hold` (revision = head). Seed: 5 пользователей,
  11 навыков, 17 RAG-документов.
- Публикация: edge `8080/8443`, web `3202`, api `127.0.0.1:8032`.

## 2. Результаты

| Проверка | Команда | Результат |
|---|---|---|
| API/БД/Redis | `staging-acceptance.ps1` | ✅ `healthz` ok, `readyz` ready, 0036/0036 |
| Admin login | там же | ✅ 200, `role=admin`, `emailVerified=true` |
| RS256/JWKS | там же | ✅ 1 ключ, `kid=staging-2026-11`, `JWT_LEGACY_HS256=false` |
| Регистрация ученика | там же | ✅ 201, `emailVerified=false` (письмо отправлено) |
| Backup-метрика | там же | ✅ `last_success_ts=1794470939`, `outbox_pending=0` |
| Observability summary | там же | ✅ `alerts=0`, `failedJobs=0` |
| Edge smoke | `smoke-prod.ps1` | ✅ healthz/readyz/SPA/HSTS/security headers |
| SMTP-транспорт | `smtp-smoke.ps1` | ✅ verification + password-reset (локальный sink) |
| SMTP боевой | `POST /auth/password-reset` | ✅ 202, `{"ok":true}`, ошибок в логах нет |
| Доставка письма | реальный ящик | ✅ «Подтвердите email — ChessClass» получено, ссылка валидна |
| S3 offsite | `backup-offsite.ps1` | ✅ `status=ok`, 208 576 Б, sha256 `6234f4c0…` |
| S3-объект | `aws s3 ls` | ✅ `chessclass-staging/chessclass-20261112T080855Z.dump.enc` |
| Restore-дрилл | `backup-restore-test.ps1` | ✅ `users=6`, `alembic=0036_s98_legal_hold` |
| Observability self-test | `observability-selftest.ps1 -Stack` | ✅ все проверки (prod-профиль, см. §3.3) |
| TLS-сертификат | `check-cert-expiry.ps1` | ✅ 364 дня |
| SPF/DKIM/DMARC | `Resolve-DnsName` | ✅ записи `iiruchating.ru` на месте |
| Proxy IP | Redis `lockout:fail:ip:*` | ✅ после фикса §3.1 — только адрес edge |
| GPU (LM Studio) | `test-gpu-tunnel.ps1` + замер | ✅ `models`/`chat` ok, **57,4 ток/с** (194 токена / 3,38 с) |

`staging-acceptance.ps1` → **exit 0**, 8/8 `OK` (outbox `SKIP` — verify-письмо
синхронное, см. runbook §4.1).

## 3. Найденные проблемы

### 3.1. P1: подмена `X-Forwarded-For` через edge (исправлено в рабочем дереве)

`deploy/nginx/edge.conf` использовал `X-Forwarded-For $proxy_add_x_forwarded_for`,
а uvicorn берёт крайний левый адрес из заголовка. Запрос с
`X-Forwarded-For: 198.51.100.7` создавал `lockout:fail:ip:198.51.100.7` —
лимиты и lockout можно обойти, подставив чужой IP.

Исправление: во всех `location` заменено на `proxy_set_header X-Forwarded-For
$remote_addr;` — клиентский заголовок отбрасывается, доверенный edge передаёт
реальный адрес. После пересоздания edge подмена не проходит
(ключ создаётся на адрес источника). **Изменение не закоммичено.**

### 3.2. P1: `deploy/jwt/private.pem` с правами 600 → 500 на логине

`gen-jwt-keys.ps1` создаёт ключ через `alpine/openssl` (root, umask 077), а API
работает под non-root и не может прочитать `/srv/jwt/private.pem`:

```
PermissionError: [Errno 13] Permission denied: '/srv/jwt/private.pem'
→ POST /api/v1/auth/login 500
```

Лечение на стенде: `chmod 644 private.pem public.pem`. Для автоматизации
рекомендуется добавить `chmod 644` в `gen-jwt-keys.ps1` (или отдельный шаг
деплоя) — иначе каждый чистый деплой ломает логин.

### 3.3. P2: staging-observability не в паритете с prod

В `docker-compose.staging.yml` профиль `observability` содержит только `tempo`,
`otel-collector`, `prometheus`, `grafana`. Сервисов `node-exporter` и
`alertmanager` нет, а `deploy/observability/prometheus.yml` не содержит
`alerting`/соответствующих targets. Поэтому `observability-selftest.ps1 -Stack`
прошёл на **prod-профиле** (его значения по умолчанию: `.env.prod.example` +
`docker-compose.prod.yml`), а не на staging. Требуется либо добавить сервисы в
staging, либо зафиксировать это как известное ограничение стенда.

### 3.4. P2: S3 — общий бакет и TTL 90 дней

Offsite-бэкапы идут в `wf-media-iilmchat` (тот же, что у workflow-builder,
`S3_PUBLIC_BUCKET=false`) с префиксом `chessclass-staging`. Lifecycle бакета —
**90 дней**, в чек-листе требуется **30**. Нужен отдельный бакет
`chessclass-backups` с правилом Expiration 30 дней (или подтвердить 90 как
приемлемое отклонение).

### 3.5. P2: edge не стартует без `grafana`

В `edge.conf` есть `location /grafana/ { proxy_pass http://grafana:3000; }`, и
nginx падает на старте, если имя `grafana` не резолвится. Поднимать стек нужно
сразу с `--profile observability`; иначе edge в цикле рестарта.

### 3.6. Info: адрес клиента на Docker Desktop

При запросах с этой машины nginx видит источником `172.30.0.1` (gateway
Docker), поэтому в lockout попадает gateway, а не `127.0.0.1`. Это артефакт
локального Docker Desktop; на хосте с публичным edge в заголовок пойдёт
реальный IP клиента.

### 3.7. Info: `backup_metric` проверяется только по API

`staging-acceptance.ps1` читает `$origin/metrics`, а edge не проксирует
`/metrics` (отдаёт SPA). Приёмку нужно запускать с
`-BaseUrl http://127.0.0.1:8032/api/v1`; TLS/edge при этом проверяются
`smoke-prod.ps1`. Альтернатива — добавить в edge отдельный `location = /metrics`
(не рекомендуется: метрики должны оставаться внутренними).

### 3.8. ✅ GPU работает, но не по схеме runbook

- Станция `DESKTOP-67ME6OH`: RTX 3060 12 GB, 32 GB RAM, LM Studio 0.4.25.
  Сервер на порту **8034** (не 1234), «Serve on Local Network» включён,
  **Require Auth выключен**.
- Доступ по Tailscale: `http://100.120.171.61:8034/v1` — отвечает с хоста и
  из контейнера `api` (23 модели).
- `test-gpu-tunnel.ps1`: `models`/`chat` OK, но `tokens_per_second=4.78` —
  артефакт короткого ответа (4 токена за 837 мс, доминирует latency).
  Корректный замер (194 токена, прогретая модель): **57,4 ток/с**.
- `.env.staging`: `LLM_LOCAL_BASE_URL=http://100.120.171.61:8034/v1`,
  `LLM_LOCAL_MODEL=qwen/qwen2.5-coder-7b-instruct`, `LLM_LOCAL_API_KEY` пуст.
  Провайдер из приложения отвечает (`answer=Париж`).
- Отклонения: нет reverse-SSH-туннеля на `172.18.0.1:8035` (станция и стенд
  в одном tailnet) и нет Require Auth. Перед prod включить ключ LM Studio и
  положить его в `LLM_LOCAL_API_KEY`.
- Failover cloud → local → echo реализован в `llm/gateway.py` и покрыт
  `test_llm_gateway.py`; live-проверка шла напрямую в local.

### 3.9. P0: ссылки из писем ведут на пустую страницу

`backend/domains/auth/router.py` формирует ссылки
`{WEB_BASE_URL}/verify-email?token=…` и `/reset-password?token=…`, но во
frontend (`frontend/src/app/App.tsx`) таких маршрутов нет. По клику из письма
открывается оболочка SPA с пустым содержимым — подтвердить email или сменить
пароль через UI нельзя. API-эндпоинты (`/auth/verify`,
`/auth/password-reset/confirm`) при этом работают.

## 4. Отклонения от Design (нужен ADR?)

- Нет: API, схема и миграции не менялись. Правка edge (§3.1) — конфигурация
  reverse-proxy, контракт S-90 не меняется.
- Приёмка на Windows/Docker Desktop, а не на Linux-хосте: часть проверок
  (реальный IP клиента, lifecycle S3, алерты) подтверждена косвенно.

## 5. Что осталось до v1.0.0

1. Добавить во frontend маршруты `/verify-email` и `/reset-password` (§3.9) —
   без них пользователь не может подтвердить email или сменить пароль.
2. Проверить заголовки письма (`spf=pass`/`dkim=pass`/`dmarc=pass`) в реальном
   ящике — доставка подтверждена, аутентификация письма пока нет.
3. GPU: включить в LM Studio Require Auth, выпустить API-key и положить его в
   `LLM_LOCAL_API_KEY`; при переходе на отдельный хост — вернуть reverse-SSH
   туннель на `172.18.0.1:8035`.
4. S3: создать бакет `chessclass-backups` (private, ru-7, vhosted) с
   lifecycle 30 дней и переключить `BACKUP_S3_*`; сейчас используется общий
   `wf-media-iilmchat` с TTL 90 дней.
5. Решить судьбу staging-observability (§3.3): паритет с prod или ограничение.
6. Live LRS/TTS (S-95) — по-прежнему ⏸️, нужно письменное решение владельца.

## 6. Риски

- `.env.staging` содержит боевые SMTP/S3-креды; файл локальный, ACL ограничен,
  в git не попадает — но при переносе стенда на сервер секреты нужно
  перевыпустить.
- `METRICS_TOKEN` в staging пуст (как в шаблоне): `/metrics` доступен без
  токена на loopback. Для prod токен обязателен.
- Пароль admin/seed сгенерирован и хранится только в `.env.staging`.
