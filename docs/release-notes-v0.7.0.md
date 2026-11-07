# Release Notes — ChessClass v0.7.0

**Дата:** 2026-11-07 · Спринты **S-81…S-85** (закрыто 3/5; S-81 и S-84
отложены) · релиз **v0.7.0 Production Readiness & Legal**.

## Что нового

### Legal & Privacy Review (S-83)
- Внутренний юридический ревью `docs/privacy-policy.md` и
  `docs/incident-response.md` по юрисдикциям **РФ / ЕС / США**:
  `docs/legal-review-v0.7.md` — матрица юрисдикций, 12 пробелов,
  16 открытых вопросов юристу, 10 остаточных рисков.
- Документы обновлены до ред. 1.1: 152-ФЗ / GDPR / COPPA, сроки уведомления
  (GDPR 72 ч), контакты `privacy@` / `security@`, retention `failed_jobs`
  90 дней и `email_outbox`.
- Consent enforcement v0.6.1: учитель класса подтверждает `age_group`
  ученика (`POST /classes/{id}/students/{id}/age-group`, поля
  `user_profiles.age_group_confirmed_at/by`, миграция
  `0034_s83_teacher_age_confirm`); self-PATCH возраста сбрасывает
  подтверждение; `/consent/status` отдаёт `ageGroup` / `teacherConfirmed` /
  `ageGroupConfirmedAt`; UI `/classes` и `/consent`.
- **Email Outbox**: таблица `email_outbox` (миграция
  `0035_s83_email_outbox`), сервис `domains/notifications` с backoff
  `min(3600, 2^n)` и парковкой после `EMAIL_OUTBOX_MAX_ATTEMPTS`, cron
  `email_outbox_deliver` каждую минуту; `POST /consent/request` больше не
  отдаёт 502 — возвращает `emailDelivered` / `emailQueued`.

### Prod-Observability (S-82)
- Профиль `observability` в `docker-compose.prod.yml` (не стартует по
  умолчанию): `tempo` (retention **168h**, mTLS на OTLP), `otel-collector`,
  `prometheus` (retention 15 дней), `alertmanager`, `grafana`.
- **Alertmanager → Telegram**: шаблон конфига рендерится entrypoint-скриптом
  (`telegram_configs`, route critical/warning, inhibit rules); секреты не
  попадают в образ.
- 5 правил алертов: `ChessClassApiDown`, `ChessClassHighErrorRate`,
  `ChessClassP95LatencyHigh`, `ChessClassDLQGrowth`,
  `ChessClassDLQGrowthRate`.
- Внутренний CA и mTLS-сертификаты — `scripts/gen-internal-certs.ps1`
  (`deploy/internal-certs/`, не в git); Grafana — только edge `/grafana/`
  или VPN, anonymous off, обязательный пароль.
- Проверка: `scripts/observability-selftest.ps1` (static) и
  `scripts/observability-selftest.ps1 -Stack` (runtime smoke).

## Отложено

| Спринт | Причина | Что нужно для запуска |
|---|---|---|
| **S-81 — Live Staging Acceptance** | Во всех env-файлах пусты боевые ключи: `LRS_ENABLED=false`, `LRS_KEY`/`LRS_SECRET`, `VOICE_API_KEY`; внешний LRS-провайдер не подключён | Ключи LRS (OAuth2) и ElevenLabs, доступ к staging и реальному LRS |
| **S-84 — GPU Tunnel on Real Station** | Нет физической Windows-станции с RTX 3060 + LM Studio для обратного SSH-туннеля | Станция, сетевой доступ, `LLM_LOCAL_BASE_URL` на staging |

Оба спринта помечены в `TODO_V0.7.md` как `⏸️ Отложен`; их DoD остаётся
открытым и переносится в v0.7.1 / v0.8.

## Числа

- Backend: **302 collected** (299 passed + 3 skipped CSP-группы); ruff/mypy — 0.
- Frontend: Vitest **5 passed**, `tsc`/build — ок.
- UI-e2e: **16 сценариев** Playwright + axe.
- Миграции: **35**, head `0035_s83_email_outbox`.
- RAG: 13/13; gold: 21/21; doc-lint: 6 checks, 0 failed.
- pip-audit: 0 известных уязвимостей.

## Обновление

```bash
git fetch --tags && git checkout v0.7.0
IMAGE_TAG=0.7.0 docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml run --rm migrate
```

- Применить миграции `0034_s83_teacher_age_confirm` и
  `0035_s83_email_outbox`.
- Задать новые env: `EMAIL_OUTBOX_MAX_ATTEMPTS`,
  `EMAIL_OUTBOX_RETENTION_DAYS`, `SMTP_*` (для реальной доставки),
  `ALERTMANAGER_TELEGRAM_*` / `TELEGRAM_*` для алертов.
- Для observability явно поднять профиль и сгенерировать сертификаты:

  ```bash
  ./scripts/gen-internal-certs.ps1
  docker compose --env-file .env -f docker-compose.prod.yml \
    --profile observability up -d
  ./scripts/observability-selftest.ps1 -Stack
  ```

## Известные ограничения

- **Live LRS/TTS** не проверены вживую: нужны боевые ключи LRS и ElevenLabs
  (S-81 отложен).
- **GPU-туннель** не проверен на реальной станции RTX 3060 (S-84 отложен).
- **Alertmanager/Telegram** проверен конфигурационно и self-test'ом; реальная
  доставка алерта требует настроенного бота и чата дежурного.
- **OTel** на проде требует доступного collector endpoint и mTLS-сертификатов;
  без них трейсы не уходят, приложение продолжает работать.
- **Юридические документы** прошли внутренний ревью, но не заменяют
  заключение юриста: 16 вопросов в `docs/legal-review-v0.7.md` открыты.
