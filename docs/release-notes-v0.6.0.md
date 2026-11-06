# Release Notes — ChessClass v0.6.0

**Дата:** 2026-11-06 · Спринты **S-75…S-80** (6/6), релиз **v0.6.0
Post-release Hardening**.

## Новое в v0.6.0

### Compliance & Email
- **SMTP-транспорт** (`core/email.py`): STARTTLS/SSL/auth, dev-console
  fallback, шаблоны verify/reset/parental-consent.
- **Enforcement согласия**: `child/teen` без `granted` получает 403
  `parental_consent_required` для LLM и PDF-отчётов; admin/auditor export —
  по правовому основанию.
- Consent-flow `/consent`: одноразовая ссылка (SHA-256, TTL 7 дней),
  подтверждение/отзыв, аудит.

### DLQ Operations
- Retention `failed_jobs` (`FAILED_JOBS_RETENTION_DAYS=90`) в cron.
- Admin API/UI `/ops`: список failed jobs и ручной retry с аудитом;
  алерт `failed_jobs_growth`, метрика `chessclass_failed_jobs`.

### Observability
- Профиль `observability`: OTel Collector → Tempo/Prometheus → Grafana,
  OTLP gRPC/HTTP, dashboard `chessclass-http-traces` (p95/error/trace_id).
- HTTP RED-метрики в `/metrics`; спаны `llm.provider.<key>`; Prometheus
  alerts (5xx, p95, DLQ).

### GPU Backend
- Отдельный `LLM_LOCAL_API_KEY` для LM Studio (`Require Auth`);
  автоматический выбор ключа по base_url, gateway передаёт его явно.
- Runbook §6: GPU через обратный SSH (RTX 3060), `GatewayPorts`, ufw,
  circuit breaker fallback.

### Integrations & A11y
- **LRS OAuth2**: Redis-кэш `lrs:oauth:token`, 401 → refresh + один повтор
  xAPI PUT; staging-env для IdP.
- **ElevenLabs TTS**: ошибки/429/пустой ключ → 429/502/503 с
  `X-Voice-Fallback: text`.
- **react-chessboard v5**: `aria-label` каждой клетки, e2e-проверка;
  axe `/chess` — 0 critical/serious.

## Числа

- Backend: **280 collected** (277 passed + 3 skipped); ruff/mypy 0.
- Frontend: Vitest 5, tsc/build ok; UI-e2e — **16 сценариев**.
- Alembic head `0033_s74_parental_consent` (**33 миграции**).
- RAG: 13/13; gold: 21/21; doc-lint: 6 checks, 0 failed; pip-audit — 0
  известных уязвимостей.

## Обновление

```bash
git fetch --tags && git checkout v0.6.0
IMAGE_TAG=0.6.0 docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml run --rm migrate
```

- Новые/уточнённые env: `SMTP_*`, `PARENTAL_CONSENT_*`,
  `FAILED_JOBS_RETENTION_DAYS`, `OBS_FAILED_JOBS_ALERT_THRESHOLD`,
  `OTEL_ENABLED`/`OTEL_EXPORTER_OTLP_ENDPOINT`,
  `LLM_LOCAL_API_KEY`, `LRS_OAUTH_*`.
- Для prod-почты и live LRS/TTS нужны боевые ключи провайдеров.
- Observability-профиль запускается явно:
  `docker compose --profile observability up -d`.

## Известные ограничения

- **Live LRS/TTS** проверены на MockTransport/fake HTTP; для staging нужны
  реальные IdP/ElevenLabs-ключи.
- **A11y-патч** опирается на `data-square` react-chessboard v5; при
  мажорном обновлении библиотеки нужен e2e-регресс.
- **OTel Collector** — dev/staging profile, не дефолт; Alertmanager/
  Telegram-доставка правил не входит в релиз.
- **SMTP** должен быть настроен оператором; dev пишет письма в лог.
- **Возраст/родитель** по-прежнему self-declared + possession of token;
  юридическая проверка privacy-policy/incident-response — на операторе.
- **Live GPU-туннель** (RTX 3060) не проверялся в CI: нет внешней станции.
- **failed_jobs** retention 90 дней; ручной retry не проверяет причину
  падения (повтор может снова упасть).
