# Отчёт: Staging Acceptance v0.8.1 (операция)

**Дата:** 2026-11-11 · **Тип:** операционная приёмка (не спринт) ·
**Версия:** v0.8.1 · **Статус:** ⏳ ожидает оператора с боевыми ключами.
**Артефакт:** `scripts/staging-acceptance.ps1` · **Runbook:**
`docs/runbooks/staging.md` §4.1–§4.2.

## 1. Что сделано

- Создан `scripts/staging-acceptance.ps1` — операционный чек-лист staging API:
  `healthz`, `readyz` (`migrationsUpToDate`), admin login, JWKS (`kid`),
  регистрация тестового ученика, проверка `email_outbox` (если доступен
  контейнер БД), backup-метрика `> 0`, observability summary/alerts без
  critical.
- Скрипт принимает `-BaseUrl`, `-AdminEmail`, `-AdminPassword`,
  `-TestStudentEmail`; опционально `-StudentPassword`, `-DbContainer`,
  `-RequireEmailOutbox`, `-SkipStudentRegistration`. Пароли/токены не
  выводятся; таблица `Check | Result | Details`; exit `0/1/2`.
- `docs/runbooks/staging.md`: разделы §4.1 «Staging Acceptance» (ключи,
  запуск, разбор каждого чека) и §4.2 «Боевые SMTP/S3» (провайдер, outbox,
  S3-консоль, lifecycle); обновлены ожидаемый alembic/версии образов.
- `docs/release-notes-v0.8.1.md`: ссылка на скрипт и чек-лист оператора
  (SMTP, S3, RS256, `PROXY_TRUSTED_HOSTS`, Sentry, observability).
- Локальная проверка скрипта — на mock-API без боевых ключей: все чеки `OK`
  (outbox `SKIP`, контейнер БД не запущен), exit `0`.

## 2. Чек-лист приёмки (ожидает оператора)

| Проверка | Ожидаемо | Статус |
|---|---|---|
| `healthz` | `status=ok`, db/redis true | ⏳ стенд |
| `readyz` | `migrationsUpToDate=true`, revision=head | ⏳ стенд |
| `admin_login` | 200 + JWT, без lockout | ⏳ оператор |
| `jwks` | непустой, есть `kid` (RS256) | ⏳ оператор |
| `student_register` | 201; письмо в реальном ящике | ⏳ оператор |
| `email_outbox` | `sent` (если строка есть) | ⏳ SMTP/БД |
| `backup_metric` | `last_success_timestamp_seconds > 0` | ⏳ S3/бэкап |
| `observability` | нет critical alerts | ⏳ стенд |
| SMTP | STARTTLS 587 / SSL 465, SPF/DKIM/DMARC | ⏳ провайдер |
| S3 | объект в bucket, sha256/size, lifecycle 30 дн | ⏳ провайдер |
| RS256 | `JWT_LEGACY_HS256=false`, ключи/kid | ⏳ оператор |
| Proxy | `PROXY_TRUSTED_HOSTS` только edge | ⏳ стенд |
| Sentry | DSN задан (опционально), PII off | ⏳ оператор |

## 3. Что не сделано / блокеры

- Боевые SMTP/S3-ключи и staging-стенд у оператора; запуск с реальными
  секретами в этой сессии **не выполнялся** (по требованию).
- Реальная доставка письма и наличие объекта в S3 подтверждаются только
  оператором через провайдера/консоль; mock-проверка покрывает логику
  скрипта, но не внешние сервисы.

## 4. Отклонения от Design (нужен ADR?)

- Нет. Acceptance — эксплуатационная проверка; API/схема не менялись.
- `email_outbox` для verify-письма может отсутствовать: auth-верификация
  отправляется синхронно через SMTP (S-75), а outbox используется для
  consent (S-83). Поэтому по умолчанию проверка outbox — `SKIP`, строгий
  режим — `-RequireEmailOutbox`; это зафиксировано в runbook.

## 5. Новые факты → Design (обязаны вернуться в Design?)

- Acceptance-контракт: `staging-acceptance.ps1` + runbook §4.1–§4.2;
  exit-коды `0/1/2`; проверка backup-метрики и observability.
- Для verify-письма проверяется реальный ящик/провайдер; `email_outbox`
  проверяется для consent-писем и при `-RequireEmailOutbox`.
- Миграции staging — `0035_s83_email_outbox`; образы `0.8.1`.
- Факты внесены в `docs/runbooks/staging.md`,
  `docs/release-notes-v0.8.1.md`, этот отчёт.

## 6. Риски

- **Секреты в истории команд.** `-AdminPassword` может попасть в history;
  использовать временный пароль/оболочку без history, не коммитить env.
- **Ложный `SKIP` outbox.** Verify-письмо синхронное; при
  `-RequireEmailOutbox` отсутствие строки станет `FAIL`, но потребуется
  consent-сценарий или отдельная запись outbox.
- **Backup-метрика = 0 до первого offsite-бэкапа.** Сначала выполнить
  `backup-offsite.ps1`, затем повторять acceptance.
- **Mock не равен провайдеру.** SPF/DKIM/DMARC, bounce, IAM/lifecycle
  проверяются только на стенде.

## 7. Следующий этап — v0.9

- Live staging с боевыми ключами LRS/TTS (S-81), реальными SMTP/S3.
- GPU-туннель RTX 3060 + LM Studio (S-84), end-to-end LLM.
- Network namespace в отдельном sandbox-контейнере
  `network_mode: none`; legal hold/retention `email_outbox`.
