# Final Acceptance — staging v0.8.1 + GPU-станция (S-100)

**Назначение.** Итоговая операционная приёмка перед выпуском **v1.0.0**:
боевые SMTP/S3/RS256, доверие к edge-прокси, GPU-туннель и observability.
Это не замена автотестам: код и контракты уже проверены `ci.ps1`/`e2e.ps1`,
здесь подтверждаются **внешние провайдеры и стенд**.

**Стенд:** staging (`docker-compose.staging.yml`, edge `https://localhost:8443`,
API `8032`, web `3202`). Порты и ADR — `docs/RULES.md` §5, запуск —
[staging.md](staging.md) §2.

**Правила:** секреты — только в `.env.staging`/`.env`, не в git и не в
отчётах; пароли/токены не печатать. Перед docker-действиями — `docker ps`
(KI-001: чужие контейнеры не трогаем). Коды `staging-acceptance.ps1`:
`0` — ok, `1` — warning, `2` — critical.

## 0. Предусловия

- [ ] Репозиторий на теге `v0.9.0` (или `main` после него), рабочее дерево
      чистое: `git describe --tags --exact-match`.
- [ ] `.env.staging` заполнен по
      [staging.md §4.1](staging.md#41-staging-acceptance-v081); секреты
      не закоммичены.
- [ ] Стек поднят и миграции применены:

  ```powershell
  docker compose --env-file .env.staging -f docker-compose.staging.yml up -d
  docker compose --env-file .env.staging -f docker-compose.staging.yml run --rm migrate
  docker compose --env-file .env.staging -f docker-compose.staging.yml ps
  ```

- [ ] `readyz` → `status=ready`, `migrationsUpToDate=true`:

  ```powershell
  Invoke-RestMethod http://127.0.0.1:8032/readyz | ConvertTo-Json -Depth 4
  ```

- [ ] Edge smoke: `.\scripts\smoke-prod.ps1 -EdgeBase https://localhost:8443
      -SkipCertificateCheck`.

## 1. SMTP

**Настройка.** В `.env.staging`:

```dotenv
SMTP_HOST=smtp.provider.example
SMTP_PORT=587                 # 587 + STARTTLS; для 465 — SMTP_SSL=true
SMTP_USER=CHANGE_ME
SMTP_PASSWORD=CHANGE_ME
SMTP_FROM=noreply@example.com
SMTP_STARTTLS=true
SMTP_SSL=false
```

**DNS (у провайдера домена):**

- [ ] SPF: `TXT @` содержит `v=spf1 include:<провайдер> ~all`; нет двух
      конфликтующих SPF-записей.
- [ ] DKIM: селектор провайдера опубликован
      (`<selector>._domainkey.example.com`), подпись проходит.
- [ ] DMARC: `_dmarc.example.com` → `v=DMARC1; p=none; rua=mailto:dmarc@example.com`
      (после стабилизации — `quarantine`/`reject`).
- [ ] `Return-Path`/bounce указывает на домен, который принимает отчёты.

Проверка записей:

```powershell
Resolve-DnsName example.com -Type TXT
Resolve-DnsName "<selector>._domainkey.example.com" -Type TXT
Resolve-DnsName _dmarc.example.com -Type TXT
```

**Проверки:**

- [ ] `.\scripts\smtp-smoke.ps1` → `verification + password-reset received`.
- [ ] `staging-acceptance.ps1` с одноразовым `-TestStudentEmail`:
      `email_outbox`/verify-письмо доставлено.
- [ ] Реальный ящик: письмо «Подтвердите email — ChessClass» пришло, не в
      Spam; заголовки `From`, `Return-Path`, `Authentication-Results`
      содержат `spf=pass`, `dkim=pass`, `dmarc=pass`.
- [ ] Consent/outbox: последние строки `sent`, без parked `failed`:

  ```powershell
  docker compose --env-file .env.staging -f docker-compose.staging.yml exec -T db `
    psql -U chess -d chessclass -c `
    "SELECT recipient, kind, status, attempts, last_error, created_at FROM email_outbox ORDER BY created_at DESC LIMIT 10;"
  ```

**Если упало:** 535 — логин/пароль; 550 — политика получателя; 421/451 —
временный отказ (retry); письмо в Spam — SPF/DKIM/DMARC и репутация домена.
Runbook: [operations §18](operations.md#18-smtp-проверка-s-93),
[staging §4.2](staging.md#42-боевые-smtps3-v081).

## 2. S3 / offsite backup

**Настройка.** В `.env.staging`:

```dotenv
BACKUP_S3_ENDPOINT=                 # пусто для AWS; URL для Yandex/VK/MinIO
BACKUP_S3_BUCKET=CHANGE_ME
BACKUP_S3_PREFIX=postgres-staging
BACKUP_S3_ACCESS_KEY=CHANGE_ME
BACKUP_S3_SECRET_KEY=CHANGE_ME
BACKUP_ENCRYPTION_KEY=              # ровно 32 hex-символа
BACKUP_EXPECTED_ALEMBIC=0036_s98_legal_hold
```

**Проверки:**

- [ ] Lifecycle на bucket: **Expiration = 30 дней** (S3 Lifecycle или
      правило провайдера); локальный `BACKUP_DIR` — 14 дней.
- [ ] Offsite-бэкап:

  ```powershell
  .\scripts\backup-offsite.ps1 -Container chessclass-staging-db `
    -BackupDir .\backups\staging
  ```

  Ожидаемо: JSON `status=ok`, `size_bytes`, `sha256`, `s3_path`.
- [ ] Объект виден в консоли провайдера/CLI; размер и дата совпадают:

  ```powershell
  aws --endpoint-url $env:BACKUP_S3_ENDPOINT s3 ls `
    "s3://$env:BACKUP_S3_BUCKET/postgres-staging/"
  ```

- [ ] Restore-test в temp PG 5439:

  ```powershell
  .\scripts\backup-restore-test.ps1 -BackupDir .\backups\staging
  ```

  Ожидаемо: `users=15`, `alembic=0036_s98_legal_hold` (или актуальный
  head), временная БД удалена.
- [ ] Метрика `chessclass_backup_last_success_timestamp_seconds > 0`;
      алерты `ChessClassBackupFailed`/`ChessClassBackupRestoreFailed` не горят.

**Если упало:** `status=error` — проверить ключи/endpoint/bucket; sha256 не
совпал — повторить бэкап; restore не видит users/alembic — проверить
`BACKUP_EXPECTED_ALEMBIC` и версию `pg_dump`. Runbook:
[operations §17](operations.md#17-offsite-бэкап-s3-s-93),
[staging §4.2](staging.md#42-боевые-smtps3-v081).

## 3. RS256 / JWKS

**Настройка:**

```powershell
.\scripts\gen-jwt-keys.ps1 -Force   # deploy/jwt/{private,public}.pem
```

```dotenv
JWT_ALGORITHM=RS256
JWT_LEGACY_HS256=false
JWT_KID=staging-2026-11
JWT_PRIVATE_KEY_PATH=/srv/jwt/private.pem
JWT_PUBLIC_KEY_PATH=/srv/jwt/public.pem
```

После изменения env — пересоздать `api`/`worker`:

```powershell
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d --force-recreate api worker
```

**Проверки:**

- [ ] `/auth/jwks` и `/.well-known/jwks.json` непустые, `kid` совпадает:

  ```powershell
  curl.exe -k https://localhost:8443/api/v1/auth/jwks
  curl.exe -k https://localhost:8443/.well-known/jwks.json
  ```

- [ ] Логин выдаёт JWT с `"alg":"RS256"` и тем же `kid` (декодировать
      header, не печатая токен в общий журнал).
- [ ] `JWT_LEGACY_HS256=false`; startup-warning о legacy-режиме отсутствует.
- [ ] `staging-acceptance.ps1` → `jwks` = OK.
- [ ] Ключи не в git: `git status --short` не показывает `deploy/jwt/*.pem`.

**Если упало:** JWKS пуст — проверить пути PEM и права; `kid` не совпал —
перевыпустить ключи и пересоздать api; старые HS256-токены не принимаются —
это ожидаемо. Runbook: [operations §9](operations.md#9-jwt-ключи-и-pii-s-47).

## 4. PROXY_TRUSTED_HOSTS

**Настройка:**

```dotenv
PROXY_TRUSTED_HOSTS=172.16.0.0/12,127.0.0.1
```

Только CIDR edge/docker-сети. `*` запрещён вне закрытого снаружи API.

**Проверки:**

- [ ] В логах/аудите входов виден **реальный IP клиента**, а не `172.x`
      edge:

  ```powershell
  docker compose --env-file .env.staging -f docker-compose.staging.yml logs --tail=100 api
  ```

- [ ] Подмена `X-Forwarded-For` с недоверенного адреса не меняет IP в
      аудите; доверенный edge — меняет.
- [ ] `tests/test_edge_auth_s90.py` зелёный (CI).
- [ ] `staging-acceptance.ps1` не показывает warning по IP/edge.

**Если упало:** в аудите `172.x` — `PROXY_TRUSTED_HOSTS` не содержит
docker-подсеть edge; поддельный IP принимается — слишком широкий CIDR или
`*`. Runbook: [operations §11](operations.md#11-защита-от-dos-и-rate-limit-s-90).

## 5. GPU-туннель

**Станция:** Windows, RTX 3060 12 GB, LM Studio + `Qwen2.5-7B-Instruct`
(Q4_K_M), порт 1234, **Require Auth**.

- [ ] На станции `GET http://127.0.0.1:1234/v1/models` отвечает; id модели
      совпадает с `LLM_LOCAL_MODEL`.
- [ ] Обратный SSH-туннель поднят (`wg-gpu-tunnel.ps1` или Scheduled Task):

  ```powershell
  powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File C:\ChessClass\wg-gpu-tunnel.ps1 `
    -ServerHost <IP-сервера> -SshUser root
  ```

- [ ] На сервере порт туннеля слушает docker gateway (не публичный
      интернет):

  ```bash
  docker network inspect chessclass-staging-net \
    --format '{{(index .IPAM.Config 0).Gateway}}'
  ```

- [ ] `test-gpu-tunnel.ps1` → `models`/`chat` («Париж»), `latency_ms`,
      `tokens_per_second` (ориентир RTX 3060: 30–50 ток/с), exit `0`:

  ```powershell
  .\scripts\test-gpu-tunnel.ps1 `
    -BaseUrl http://172.18.0.1:8035/v1 `
    -ApiKey '<токен LM Studio>' `
    -Model qwen2.5-7b-instruct
  ```

- [ ] В `.env.staging`: `LLM_LOCAL_FALLBACK=true`,
      `LLM_LOCAL_BASE_URL=http://172.18.0.1:8035/v1`,
      `LLM_LOCAL_MODEL=<id из /models>`, `LLM_LOCAL_API_KEY=<токен>`;
      api/worker перезапущены.
- [ ] Live-запрос через шлюз отвечает; при остановке LM Studio срабатывает
      fallback cloud → local → echo, breaker local открывается после 5 ошибок.
- [ ] Firewall: gateway:8035 доступен только из docker bridge; LM Studio не
      опубликован в интернет.

**Если упало:** `401` — токен; `404 model` — неверный `LLM_LOCAL_MODEL`
(облачный slug вместо id LM Studio); timeout — туннель/SSH; низкие
ток/с — GPU offload/context. Runbook:
[llm-gateway §6](llm-gateway.md#6-gpu-инференс-через-обратный-ssh-rtx-3060-windows)
и §7.

## 6. Observability

- [ ] Static: `.\scripts\observability-selftest.ps1` — 12 правил, promtool,
      alertmanager, redact-logs, cert-expiry OK.
- [ ] Runtime: `.\scripts\observability-selftest.ps1 -Stack` — mTLS-трейс
      доходит до Tempo, маршруты алертов проверены; профиль остановлен,
      volumes сохранены.
- [ ] Prometheus targets `chessclass-api` и `otel-collector` — `up`; в
      `/api/v1/rules` 12 правил `ChessClass*`.
- [ ] `/admin/observability/alerts` (admin) — **нет critical**;
      `ChessClassBackupFailed`, `ChessClassBackupRestoreFailed`,
      `ChessClassRetentionFailed` не горят. Info-алерт
      `ChessClassLegalHoldActive` допустим, если hold действительно активен.
- [ ] Тестовый алерт доходит в Telegram/email и приходит `resolved`
      (operations §10.6).
- [ ] `check-cert-expiry.ps1` — нет critical (< 7 дней).

**Если упало:** нет трейса — `OTEL_ENABLED`, endpoint collector, mTLS
сертификаты; target down — `METRICS_TOKEN`; critical-алерт — разобрать по
`/admin/observability/alerts` и §10 operations. Runbook:
[operations §10](operations.md#10-prod-observability-s-82) и
[§7.1](operations.md#71-ротация-внутренних-сертификатов-без-простоя-s-88).

## 7. Итоговая приёмка

```powershell
.\scripts\staging-acceptance.ps1 `
  -BaseUrl https://localhost:8443/api/v1 `
  -AdminEmail admin@example.com `
  -AdminPassword '<боевой-пароль>' `
  -TestStudentEmail accept-YYYY-MM-DD@example.com
```

- [ ] Код `0` (или `1` только с разобранным warning); critical нет.
- [ ] Отчёт оператора заполнен: дата, стенд, версия `v0.9.0`, результаты
      SMTP/S3/RS256/PROXY/GPU/Observability, ссылки на логи (без секретов).
- [ ] Отчёт сохранён как `docs/sprint-reports/staging-acceptance-YYYY-MM-DD.md`.

| Чек | Команда | Ожидаемо | При провале |
|---|---|---|---|
| API/БД/Redis | `staging-acceptance.ps1` | `healthz`/`readyz` ok | [staging §4.1](staging.md#41-staging-acceptance-v081) |
| SMTP | `smtp-smoke.ps1` + реальный ящик | письмо, SPF/DKIM/DMARC pass | [operations §18](operations.md#18-smtp-проверка-s-93) |
| S3 | `backup-offsite.ps1` | `status=ok`, sha256 | [operations §17](operations.md#17-offsite-бэкап-s3-s-93) |
| Restore | `backup-restore-test.ps1` | users/alembic ok | [operations §17](operations.md#17-offsite-бэкап-s3-s-93) |
| RS256 | `/auth/jwks` | `kid`, RS256 | [operations §9](operations.md#9-jwt-ключи-и-pii-s-47) |
| Proxy IP | логи/аудит | реальный IP клиента | [operations §11](operations.md#11-защита-от-dos-и-rate-limit-s-90) |
| GPU | `test-gpu-tunnel.ps1` | chat + ток/с, exit 0 | [llm-gateway §6](llm-gateway.md#6-gpu-инференс-через-обратный-ssh-rtx-3060-windows) |
| Observability | `observability-selftest.ps1 -Stack` | трейс + маршруты, нет critical | [operations §10](operations.md#10-prod-observability-s-82) |

## 8. Решение о v1.0.0

v1.0.0 выпускается **только если**:

1. все P0-пункты выше отмечены и `staging-acceptance.ps1` не вернул `2`;
2. GPU-станция отвечает через `test-gpu-tunnel.ps1`;
3. live LRS/TTS подтверждены **или** владелец проекта письменно зафиксировал
   их как известное ограничение v1.0.0 (S-95 ⏸️);
4. отчёт приёмки сохранён и приложен к S-101.

Иначе — фиксируем блокер в `TODO_V1.0.md` S-101 и повторяем приёмку после
устранения. Откат стенда — [staging §6](staging.md#6-остановка-и-очистка),
prod-откат — [operations §13](operations.md#13-релизы-из-ghcr-и-rollback-s-92).
