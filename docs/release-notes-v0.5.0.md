# Release Notes — ChessClass v0.5.0

**Дата:** 2026-11-06 · Спринты **S-70…S-74** (5/5), этап **v0.5.0
Hardening & Compliance** ✅.

## Новое в v0.5.0

### Надёжность LLM
- **Circuit breaker per provider** (S-70): Redis-состояния
  CLOSED → OPEN → HALF_OPEN, 5 ошибок за 60 с, один probe, recovery.
- **Retry с экспоненциальным backoff и jitter**, разделение
  `failover:*` / `quota_*` в `llm_calls`.

### OWASP LLM Top 10
- **Instruction isolation** (S-71): trusted/untrusted-блоки в промптах,
  санитизация role-меток и служебных токенов.
- **Output guardrails**: нейтрализация HTML/JS, редактирование
  секретоподобных строк; adversarial-матрица LLM01/LLM02/LLM06.
- **Блокирующие RAG-гейты** в CI: `chess_rag_eval.py` (13/13) и
  `rag_gold_check.py` (21 кейс).

### Multi-tenant DB Isolation
- **PostgreSQL RLS** (S-72) на `bot_stats`, `cognitive_skill_events`,
  `anticheat_flags`: admin — всё, ученик — свои строки, учитель — ученики
  своих классов.
- Контекст `app.current_user_id`/`app.current_user_role` через `SET LOCAL`
  на соединении из пула; `FORCE RLS` + роль `chess_app` (`NOBYPASSRLS`).
- Интеграционные тесты сырым SQL: учитель A/B, admin, переключение A→B→A.

### Async Reliability & Tracing
- **Идемпотентность arq** (S-73): `_job_id` для матчей/анализа PGN/турниров,
  повторный HTTP-запрос матча не создаёт дубль. Интерактивный
  `analyze_position` оставлен без `_job_id`, чтобы retry после timeout не
  получал `task_busy`.
- **DLQ `failed_jobs`**: `job_id`, `attempts`, `trace_id`, текст ошибки;
  `WORKER_MAX_TRIES`, обёртка `track_job`.
- **OpenTelemetry**: `trace_id` из API → arq → LLM, JSON-логи,
  `llm_calls.trace_id`, спаны `http.request`/`arq.*`/`llm.generate`;
  OTLP HTTP exporter опционален.
- Hash-lock обновлён под OTel SDK/exporter; `pip-audit` — без известных
  уязвимостей.

### Compliance
- **Parental consent workflow** (S-74): запрос согласия, одноразовая ссылка
  на 7 дней (в БД только SHA-256), подтверждение/отзыв, аудит, UI
  `/consent`.
- **Политика конфиденциальности** `docs/privacy-policy.md` и
  **план реагирования** `docs/incident-response.md` (GDPR 72 ч, роли,
  чек-листы, учения).
- Возрастные группы `child/teen` требуют согласия; `adult` —
  `not_required`; `unknown` можно заполнить в профиле.

## Числа

- Backend: **268 collected** (265 passed + 3 skipped; включая 4 теста
  consent); ruff/mypy 0; `pip-audit` — 0 известных уязвимостей.
- Frontend: Vitest 5, `tsc`/build — ok; UI-e2e — **15 сценариев**
  (добавлен consent-flow), axe — 0 critical/serious.
- Alembic head `0033_s74_parental_consent` (**33 миграции**).
- RAG: 13/13; gold: 21/21; doc-lint: 6 checks, 0 failed.

## Обновление

```bash
git fetch --tags && git checkout v0.5.0
IMAGE_TAG=0.5.0 docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml run --rm migrate
```

- Новые env: `OTEL_ENABLED`, `OTEL_SERVICE_NAME`,
  `OTEL_EXPORTER_OTLP_ENDPOINT`, `WORKER_MAX_TRIES`,
  `PARENTAL_CONSENT_TTL_DAYS`, `PARENTAL_CONSENT_POLICY_VERSION`.
- Для prod-почты родительского согласия нужен SMTP-транспорт (в dev —
  консольный лог `[dev-email]`, как verify-email).
- Перед публикацией проверьте контакты/реквизиты в privacy-policy и
  incident-response.

## Известные ограничения

- **Live TTS ElevenLabs** — гео-блок из РФ; альтернативный провайдер —
  backlog.
- **react-chessboard v5** — часть клеток без aria-label (third-party);
  исключено из axe-гейта.
- **Live LRS-провайдер** — OAuth2/mapping проверены на mock/локальном
  контуре; живой IdP требует настройки.
- **OTel Collector** не входит в compose; без endpoint спаны создаются,
  но не экспортируются.
- **`failed_jobs` retention** и ручной retry из DLQ — backlog.
- **Parental consent email** в prod требует SMTP-интеграции; токен-ссылка
  и аудит уже реализованы.
