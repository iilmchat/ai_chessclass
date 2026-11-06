# CHANGELOG — ChessClass

Формат — по мотивам [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/);
версии соответствуют этапам дорожной карты (`TODO_V0.1.md` — архив,
`TODO_V0.2.md` — архив, `TODO_V0.3.md` — v0.3.0, `TODO_V0.4.md` — v0.4.0).
Детали — в `docs/sprint-reports/`.

## [Unreleased] — v0.7.0

### Добавлено

#### S-83 — Legal & Privacy Review (2026-11-06)
- Внутренний юр-ревью privacy-policy/incident-response по юрисдикциям
  РФ/ЕС/США: `docs/legal-review-v0.7.md` (матрица юрисдикций, 12 пробелов,
  16 открытых вопросов юристу, 10 остаточных рисков); документы — ред. 1.1
  (152-ФЗ/GDPR/COPPA, сроки уведомления, контакты, retention `failed_jobs`
  90 дней, `email_outbox`).
- Consent enforcement v0.6.1: учитель класса подтверждает `age_group`
  ученика (`POST /classes/{id}/students/{id}/age-group`,
  `user_profiles.age_group_confirmed_at/by`, миграция
  `0034_s83_teacher_age_confirm`); self-PATCH возраста сбрасывает
  подтверждение; `/consent/status` отдаёт `ageGroup`/`teacherConfirmed`/
  `ageGroupConfirmedAt`; UI `/classes` и `/consent`.
- SMTP retry/очередь писем parental consent: таблица `email_outbox`
  (миграция `0035_s83_email_outbox`), сервис `domains/notifications` с
  backoff `min(3600, 2^n)` и парковкой после `EMAIL_OUTBOX_MAX_ATTEMPTS`,
  cron `email_outbox_deliver` каждую минуту; `POST /consent/request` больше
  не отдаёт 502 — возвращает `emailDelivered`/`emailQueued`.
- Тесты: `test_teacher_age_confirmation.py` (+4), `test_email_outbox.py`
  (+6); backend — 290 collected (287 passed + 3 skipped).

### Изменено
- `scripts/doc_lint.py` — активный план `TODO_V0.7.md`, прогресс v0.7;
  README/Design/SPEC/CHANGELOG обновлены (35 миграций, head
  `0035_s83_email_outbox`).

### Исправлено
- `scripts/ci/backup_smoke.sh`: ожидаемый alembic-head выводится из
  `alembic heads` вместо хардкода `0030_s67_lms_oauth` — GitHub Actions
  job `e2e` снова проходит шаг backup→restore smoke (падал с S-72).

## [0.6.0] - 2026-11-06

### Добавлено

#### S-80 — Release v0.6.0 (2026-11-06)
- Версия 0.6.0 во всех источниках, IMAGE_TAG, release notes, тег `v0.6.0`.
- Финальные CI/e2e, staging `config -q`, pip-audit; счётчики 280 collected /
  33 миграции / 16 e2e.

#### S-79 — Integrations (LRS, TTS) & a11y Chessboard (2026-11-06)
- LRS OAuth2: Redis-кэш `lrs:oauth:token`, обновление при 401 и повтор xAPI
  PUT; MockTransport-тест; staging-env для OAuth2.
- ElevenLabs TTS: 429/ошибка/пустой ключ → HTTP 503/429/502 с заголовком
  `X-Voice-Fallback: text`; тесты квоты/fallback.
- react-chessboard v5: `aria-label` для каждой клетки («Белая пешка на e2»,
  «Пустая клетка e4»); e2e-проверка + axe 16 сценариев.

#### S-78 — Infrastructure: GPU Backend Support (2026-11-06)
- `LLM_LOCAL_API_KEY` для LM Studio (`Require Auth`) в config/env;
  отдельный от облачного `LLM_API_KEY`.
- `OpenAICompatProvider` выбирает локальный ключ при совпадении base_url;
  gateway передаёт ключ в `get_local_provider`.
- Runbook §6: GPU-инференс через обратный SSH (RTX 3060), LM Studio,
  `GatewayPorts`, ufw и `.env`-пример.

#### S-77 — Observability v0.6 (2026-11-06)
- Compose-профиль `observability`: OTel Collector → Tempo/Prometheus →
  Grafana; OTLP gRPC/HTTP endpoint, dev/staging порты.
- Grafana dashboard `chessclass-http-traces`: p95 latency, 5xx/all rate,
  DLQ и Tempo traces с `trace_id`.
- HTTP RED-метрики в `/metrics` (`chessclass_http_requests_total`,
  `chessclass_http_request_duration_seconds_*`); спаны
  `llm.provider.<key>`; config-тесты и валидация collector.

#### S-76 — DLQ Operations & Retention (2026-11-06)
- Retention `failed_jobs` (`FAILED_JOBS_RETENTION_DAYS=90`) в общем cron.
- Admin API/UI `/admin/observability/failed-jobs` и ручной retry с аудитом;
  повторная постановка в правильную arq-очередь для `run_match`.
- Алерт `failed_jobs_growth`, метрика `chessclass_failed_jobs`, панель DLQ
  в `/ops`; тест list/retry/alert/retention.

#### S-75 — Consent Enforcement & Email Delivery (2026-11-06)
- SMTP-транспорт `core/email.py` (STARTTLS/SSL, auth, timeout;
  dev-console fallback) для verify/reset/parental-consent; `SMTP_*` env.
- Enforcement: child/teen без `granted` → 403 `parental_consent_required`
  для LLM (`_llm_generate`) и PDF-отчётов; admin/auditor export — по
  правовому основанию.
- Тесты `test_email.py` (dev/success/failure), consent-gate LLM;
  backend — 272 collected.

## [v0.5.0] — 2026-11-06

### Добавлено

#### S-74 — Compliance & Release v0.5.0 (2026-11-06)
- Parental consent workflow (COPPA/GDPR-K): `parental_consents`, одноразовая
  ссылка (SHA-256, TTL 7 дней), `/consent/{status,request,confirm,revoke}`,
  UI `/consent`, аудит; миграция `0033`.
- `docs/privacy-policy.md`, `docs/incident-response.md`,
  `docs/release-notes-v0.5.0.md`; e2e consent-flow.
- Версия **v0.5.0** во всех источниках, IMAGE_TAG, README/Design/CHANGELOG.

#### S-73 — Async Reliability & Tracing (2026-11-06)
- Идемпотентность arq: `_job_id` для матчей/анализа/турниров; повторный
  HTTP-запрос матча возвращает существующий `matchId`.
- DLQ `failed_jobs` + `track_job`: ошибки задач с `job_id`, `attempts`,
  `trace_id`; `WORKER_MAX_TRIES` (`max_tries`).
- OTel tracing: `http.request` → `arq.*` → `llm.generate`, `trace_id` в
  JSON-логах, аргументах arq и `llm_calls.trace_id`; OTLP HTTP exporter.
- Миграция `0032_s73_async_tracing`; 5 новых тестов, backend — 264 collected;
  hash-lock обновлён (`opentelemetry-sdk`, OTLP exporter).

#### S-72 — Multi-tenant DB Isolation / RLS (2026-11-05)
- PostgreSQL RLS на `bot_stats`, `cognitive_skill_events`, `anticheat_flags`:
  admin — все строки; ученик — свои; учитель — строки учеников своих классов
  (через `class_members` → `classes.teacher_id`).
- Транзакционно-локальный контекст `app.current_user_id` /
  `app.current_user_role` в `core/db.py`; HTTP-middleware из JWT, arq-задачи
  получают `user_id`/`role` аргументами. Приложение работает под
  непривилегированной ролью `chess_app` (`NOLOGIN NOBYPASSRLS`).
- Миграция `0031_s72_rls_isolation` (ENABLE + FORCE RLS, обратимый
  downgrade, без backfill); 6 RLS-тестов, backend — 259 collected.
- README/Design/TODO: счётчики 259 тестов, 31 миграция, ADR-015 уточнён.

#### S-71 — OWASP LLM Hardening & CI Eval (2026-11-04)
- Instruction isolation в `prompts/builder.py`: trusted/untrusted-блоки,
  санитизация служебных токенов и role-меток (LLM01).
- Output guardrails `llm/security.py`: нейтрализация HTML/JS (LLM02) и
  редактирование секретоподобных строк в промпте/ответе (LLM06).
- Блокирующие RAG-гейты в CI: `chess_rag_eval.py` и `rag_gold_check.py`.
- Adversarial-матрица `tests/test_prompt_injection.py`; `PROMPT_VERSIONS` → 2.

#### S-70 — LLM Gateway Resilience (2026-11-04)
- Redis circuit breaker провайдеров (`closed`/`open`/`half_open`, 5 ошибок
  за 60 с, recovery 60 с, один probe через `SET NX`).
- Retry LLM-клиента — экспоненциальный backoff с jitter.
- `fallback_from` разделён: `failover:*` (ошибка/CB/нет конфигурации) и
  `quota_*` (квота).

## [v0.4.0] — 2026-11-04

### Добавлено

#### S-69 — Релиз v0.4.0 (2026-11-04)
- Версия 0.4.0 (backend/frontend/API/IMAGE_TAG), миграция head 0030,
  e2e 14 сценариев, backend 235 collected.
- Тег `v0.4.0`, release-notes `docs/release-notes-v0.4.0.md`, runbook
  `docs/runbooks/release-v0.4.0.md`; staging/prod приёмка — фиксированные
  ограничения (живые ключи unavailable локально) в runbook §5.
- Backlog v0.5: live-TTS ElevenLabs (geo-block), react-chessboard v5
  a11y, live LRS-провайдер, gamification.

#### S-68 — Telegram webhook, teacher-события, алерты (2026-11-04)
- `POST /telegram/webhook`: secret `TELEGRAM_WEBHOOK_SECRET`
  (X-Telegram-Bot-Api-Secret-Token; пусто → 404), `/start <link_code>`
  — связывание через Redis-код, `/stop` — отписка, прочее — help;
  long-poll fallback `poll_updates_once` (getUpdates, offset в Redis,
  Redis-лок) + worker-cron `telegram_poll` (2 мин).
- Teacher-события: `enqueue_teacher_events` учителям всех классов
  ученика (kind: submission/tournament/complaint; хуки в progress/
  tournaments/pvp); алерты `telegram_outbox_failed` и
  `lrs_deliveries_failed` в `/ops`.
- Тесты `test_telegram_webhook.py` (+8); env во всех `.env*.example`.

#### S-67 — LRS OAuth2 и LMS-mapping (2026-11-04)
- Миграция `0030_s67_lms_oauth`: `lms_courses`, `lms_class_map`
  (class unique, activity_ref), FK на classes/lms_courses.
- OAuth2 client_credentials (`lrs_oauth_*`): Bearer с токен-кэшем и
  refresh за 60 c до expiry; Basic — fallback; `lrs_oauth_token_url`
  в egress-allowlist. CRUD `/admin/lms/courses|class-map` +
  `/oauth-status` (audit, teacher/admin read); skill-объекты мапнутых
  классов ссылаются на activity_ref курса.
- Админ-панель LMS в `/ops`; тесты `test_lms_oauth.py` (+5).

#### S-66 — A11y/mobile гейт и e2e 14 (2026-11-03)
- axe-core гейт 2 теста (гость 6 маршрутов + admin все 14,
  wcag2a/2aa); aria-live 6 страниц; контраст `.achievement.locked`
  2.42→4.63:1; select/file-input aria-label; mobile ≤720px +
  `overflow-wrap` (320px/200%); a11y-audit.md — все пункты зелёные.
- e2e `screens.spec.ts` +4 (RAG publish/review/ops/telegram-link) —
  UI-e2e **14**; infer react-chessboard v5 cells — third-party backlog.

#### S-65 — PvP UI и workflow жалоб (2026-11-03)
- Страница `/pvp` (любая роль): выбор бота (rated-флаг), создание комнаты,
  quick-match, вход по коду, статус-карточка с поллингом (waiting→ready→
  running→done), отмена (host), старт (host), SSE-строка прогресса,
  реплей с шахматной доской (шаги по полуходам), PvP-лидерборд, отправка
  жалобы участником.
- Страница `/complaints` (teacher/admin): очередь жалоб (фильтр статуса),
  вердикт reviewed/rejected с note → `PATCH /admin/pvp/complaints/{id}`.
- Миграция `0029_pvp_complaint_review`: `reviewed_by`/`reviewed_at`/`note`.
- Backend: ревью-контракт (статус-машина, RBAC teacher/admin, аудит
  pvp.complaint.review); тесты +3 (flow, rejected/bad-status, teacher).
- e2e `pvp.spec.ts`: два браузера (host/guest) играют матч до done и
  видят реплей; жалоба закрывается админом в UI.
- Навигация: `/pvp`, «Жалобы».

#### S-64 — RAG-редактор UI и gold-set eval (2026-11-03)
- Страница `/rag` (teacher/admin, доступ по роли): список документов с
  фильтром статусов, редактор (создание черновика / правка → новая версия),
  панели версий с rollback, импорт файлом (.md/.txt/.pdf → base64 → draft),
  поиск-превью топ-5 (published), панель eval.
- **Gold-set eval 3→21 кейса** (`rag/eval_cases.py`, подстроки от
  сид-корпуса 17 доков; sentinel-скрипт `scripts/rag_gold_check.py`);
  `GET /admin/rag/eval` дополнен `results` (по кейсу: vectorHit/hybridHit).
- Deps: axe-core остаётся devDep (S-63); новых пакетов нет.

#### S-63 — Ворота CI (2026-11-03)
- Gate-матрица: backend + **pip-audit** (по `requirements.lock`), e2e +
  **axe-core** (0 critical/serious на 5 маршрутах; скрипт из node_modules) +
  **backup→restore smoke** (`scripts/ci/backup_smoke.sh`), jobs **secrets**
  (gitleaks) и **images** (docker build api/web).
- `.github/workflows/load.yml` — cron пн 04:00 UTC + workflow_dispatch;
  load_smoke 100/20 с публикацией p95 в Step Summary.
- axe-core в devDeps; README: CI-описание, UI-e2e 7→8.

#### S-62 — Hash-lock сборка (2026-11-03)
- `backend/requirements.lock` — `pip-compile --generate-hashes` из
  pyproject (46 пакетов, каждый с `--hash=sha256`); сборка Dockerfile —
  `--require-hashes` по lock + сам пакет `--no-deps`.
- SHA256 архива Stockfish 17.1 pinned (`ARG STOCKFISH_SHA256`), проверка
  в heredoc → подмена архива ломает build.
- `backend/scripts/pip_audit.sh` — pip-audit по lock (DoD no known).
- Release-truth tests (+3): lock-файл с хэшами, Dockerfile из lock, SF-hash.
- Резидуал (→S-63): PEP 517 build-isolation на setuptools вне hash-lock
  (документировано SPEC §3.30).

#### S-61 — CSP и egress-allowlist (2026-11-03)
- **CSP** в web-nginx (`frontend/nginx.conf`, enforce) + режим
  `CSP_MODE=report-only` для staging (entrypoint-скрипт; audit Vite
  inline-стилей → allowlist `style-src 'unsafe-inline'`, скрипты self);
  edge не дублирует (заголовок проходит сквозь).
- **Egress allowlist** `core/egress.py`: hook на все исходящие
  httpx-клиенты (LLM/voice/Telegram/LRS) — loopback + `ALLOWED_EGRESS_HOSTS`
  (host/`*.host`) + настроенные базовые URL; нарушение → 502
  `egress_blocked` (bypass-тест тем же клиентом краснеет).
- Env: `ALLOWED_EGRESS_HOSTS` (все три примера), `CSP_MODE` (staging);
  `env_ignore_empty` в Settings (пустая env = дефолт из кода).
- Tests +13 (egress 8 / CSP release-truth 3 / env-контракт 2); dev-compose
  api монтирует репо в `/repo:ro` для doc-lint/release-truth тестов.
- `.env.prod` добавлен в `.gitignore` (секреты только локально).

#### S-58 — Staging-контур и CORS (2026-11-03)
- `docker-compose.staging.yml` + `.env.staging.example`: prod-parity staging
  (11 сервисов), порты pg **5440** / redis **6387** / api **8032** / web
  **3202** / edge **8080+8443** (ADR-014), отдельные volumes и сеть,
  `APP_ENV=staging`, `WEB_BASE_URL=https://localhost:8443`.
- `CORS_ORIGINS` (comma/JSON, `NoDecode`) в `core/config.py`; allowlist в
  `CORSMiddleware` вместо хардкода localhost; warning, если в staging/prod
  остались localhost-источники.
- `docs/runbooks/staging.md`: подъём/миграции/seed, smoke, CORS, backup/restore,
  env-дифф dev/staging/prod, ограничения.
- Brand стадии из build-arg `APP_STAGE`: staging-образ
  `chessclass/frontend:0.3.0-staging` показывает «v0.3.0 · staging», prod —
  «prod».
- Исправлено: `/readyz` отдавал версию **0.1.0** из `app/__init__.py` — теперь
  `0.3.0`; e2e redis host-порт **6385→6386** (KI-001: 6385 занят
  `ai-chess-annotator-redis-1`).

#### S-59 — Живая приёмка LLM и voice (2026-11-03)
- `backend/scripts/llm_smoke.py` v2: `--mode auto|echo|live`, JSON-артефакт
  (schema `chessclass.llm_smoke/1`), `--compare` echo→live, `--with-voice`,
  `--with-pdf`, health провайдера, FinOps-сверка (`llm_calls` + суммы за
  сутки); коды возврата 0/2/3; +3 unit-теста (`tests/test_llm_smoke.py`).
- Echo-базлайн staging: 4/4 `status=echo model=echo cost=0.0000`,
  `voice=disabled`, `pdf=ok`; артефакт
  `docs/sprint-reports/S-59-echo-baseline-2026-11-03.json`.
- **Live LLM (RouterAI):** `health=ok`, `missingModels=[]`, **4/4
  `status=ok`** (L1 `qwen/qwen3.7-flash`, L2 `deepseek/deepseek-v4.1-flash`,
  L3 `anthropic/claude-sonnet-5.5`, judge `google/gemini-3.1-flash-lite`),
  cost **1.3629 ₽** (961/5291 токенов), PDF `ok`, diff echo→live **4/4**;
  артефакт `docs/sprint-reports/S-59-live-2026-11-03.json`.
- Каталог RouterAI сверён 2026-11-03 (582 модели): слаги/цены ₽/1M
  зафиксированы в `.env.example`/`.env.prod.example`/`.env.staging.example`
  и runbook `llm-gateway.md` §1; latency 11–26 с — §5.
- Voice: ElevenLabs geo-block из РФ (`geo-restriction.elevenlabs.io`) —
  живой TTS не принят, voice остаётся graceful off; вынесено в backlog
  (альтернативный TTS-провайдер).
- Runbooks: `llm-gateway.md` §1/§2.2/§5/§7, `staging.md` §8; TODO_V0.4
  S-59 → ✅.

#### S-60 — Правда релиза и doc-lint (2026-11-03)
- `scripts/doc_lint.py` (stdlib): версии (`pyproject.toml`/`package.json`/
  `app/__version__`/FastAPI/`IMAGE_TAG`), alembic head+count против README,
  счётчики backend/frontend/e2e, единственный активный план (`TODO_V0.4`),
  запрещённые стрейл-маркеры (`16/16`, `174 passed`, `0021_tournaments`,
  `v0.2.0 Draft`), прогресс TODO_V0.4; `--tests-count auto|N`.
- CI: шаг «Doc-lint (release truth)» в `.github/workflows/ci.yml` (backend job,
  после pytest — сверка счётчика с фактическим collection).
- README: backend-тесты 200→**203** (+3 doc-lint), RAG-док seed 13→**17**;
  `docs/README` — CHANGELOG (S-60); RULES §6 — команда doc-lint.
- 3 unit-теста `backend/tests/test_doc_lint.py` (чистые хелперы линта).

### Документация

- README/Design/TODO_V0.3/статусы документов приведены к факту релиза v0.3.0:
  возможности, 12/12 спринтов (S-46…S-57, E-17…E-20), 195 backend-тестов,
  head `0028_rag_editor` (28 миграций), версия Design v0.3.0.
- Brand и prod-образы версионированы: бренд/версия из build-env, теги
  образов `IMAGE_TAG` в `docker-compose.prod.yml`.
- Runbook `docs/runbooks/release-v0.3.0.md` §7: `--notes-file
  docs/release-notes-v0.3.0.md`; синхронизация `IMAGE_TAG`, git-тега и версий.
- Добавлен `TODO_V0.4.md` — план v0.4.0 (S-58…S-69, этапы E-21…E-24).

## [v0.3.0] — 2026-11-03

### Добавлено

#### S-57 — Релиз v0.3.0 (2026-11-03)
- Тег `v0.3.0`, GitHub Release, release-notes; CI backend/frontend/e2e
  зелёный.
- Demo-обход по e2e/тестам/API: ученик, учитель, родитель, auditor, admin;
  известные ограничения зафиксированы.
- Backlog v0.4 — в release-notes.

#### S-46 — Retention, наблюдаемость и стоимость (2026-11-02)
- Миграция `0022_observability`: `voice_usage` (кто/сколько/стоимость,
  cache-hit) для cost-per-student.
- `domains/retention`: gzip-архив + удаление `audit_logs`, `llm_calls`,
  `voice_audio` (+файлы), `voice_usage`, старых draft/rejected `chess_studies`;
  dry-run; worker cron 04:10 UTC.
- `/metrics` Prometheus (DB/Redis, очереди, LLM/voice cost, диск);
  `/admin/observability/summary|alerts|costs|costs.csv|retention/*`;
  UI `/ops` (стоимость, алерты, retention).
- `METRICS_TOKEN`/retention env; prod volume `chessclass_archive`.
- Тесты: архив/удаление/сохранение published, dry-run, metrics/costs/retention;
  backend 176.

#### S-47 — Auth-hardening и приватность (2026-11-02)
- RS256/JWKS: `JWT_ALGORITHM`, private/public keys/paths, `JWT_KID`,
  `JWT_LEGACY_HS256`; `/api/v1/auth/jwks` и `/.well-known/jwks.json`;
  `scripts/gen-jwt-keys.ps1` + `deploy/jwt`.
- Аудит `auth.login.success/failed`, `auth.role.change`,
  `auth.auditor_scope.change`, `auth.user.anonymize`; admin endpoints
  role/scope/anonymize.
- Auditor scope: `flags`, `audit`, `reports`, `observability` (admin
  управляет через `/admin/users/{id}/auditor-scope`).
- PII: анонимизация email/пароля/профиля, деактивация и отзыв refresh;
  age_group/PII-политика в SPEC/runbook.
- Security-тесты: RS256/JWKS, legacy HS256, alg=none/HS512, role/scope/
  anonymize; backend 179.

#### S-48 — Турниры v2: async, replay и античит (2026-11-02)
- Миграция `0023_tournament_v2`: `progress/total_matches/job_id/cancel_requested/
  error`, `tournament_moves` (ply/fen/uci/agent/think_ms/sf_sample).
- arq `run_tournament_job` + recovery-cron `resume_tournaments`; API create
  возвращает 202/queued, SSE `/tournaments/{id}/events`; cancel endpoint.
- Запись ходов и replay `/tournaments/{id}/matches/{matchId}/replay`;
  SF-семплирование и `engine_likeliness` для турнирных ботов.
- UI: polling прогресса, отмена, replay; bracket 8 ботов — 7 матчей.
- Тесты: async job/replay/idempotency/cancel/SSE; backend 181.

#### S-49 — LMS LRS-адаптер и scheduled export (2026-11-02)
- Миграция `0024_lms`: `lrs_deliveries` (unique statement_id, payload,
  status/attempts/next_attempt/sent_at).
- xAPI builder по ученикам/навыкам/бот-Elo; идемпотентная очередь
  (UUID5 за день), retry/backoff; `LRS_ENABLED/ENDPOINT/KEY/SECRET`.
- Worker `lms_sync` (minute=15, startup); admin
  `/admin/lms/{status,sync,deliveries,deliveries.csv}`; журнал доставки.
- Тесты: повтор не дублирует, retry после 500, status/CSV/sync; backend 183.

#### S-50 — Telegram-бот: уведомления (2026-11-03)
- Миграция `0025_telegram`: `telegram_links` (chat_id/consent) и
  `telegram_outbox` (status/attempts/next_attempt/sent_at).
- `/telegram/status|link|link-code|confirm`, DELETE `/link`; consent обязателен,
  код/deep-link через Redis TTL; отписка удаляет привязку.
- Outbox: бейджи, стрики, проверка/PDF; retry/backoff; rate-limit 20/сутки;
  worker `telegram_deliver` (minute=2/startup).
- Без `TELEGRAM_BOT_TOKEN` — graceful off (`disabled=1`), секреты не логируются;
  UI в профиле. Тесты на fake sender; backend 186.

#### S-51 — PvP-матчи ботов (2026-11-03)
- Миграция `0026_pvp`: `pvp_rooms` (код/участники/статус/rated),
  `pvp_ratings` (отдельный Elo), `pvp_complaints`.
- Комнаты/приглашения, join по коду, quick-match ±300 PvP Elo; лимиты
  комнат/quick 10/мин; start создаёт bracket-турнир 2 ботов + arq-job.
- SSE `/pvp/rooms/{id}/events`, replay, leaderboard, зрители; отдельный
  PvP-Elo (K=24); финализация из tournament-job; жалобы + admin list.
- Тесты: комната/join/start/рейтинг/leaderboard/жалобы/quick; backend 188.

#### S-52 — Spaced-repetition тренажёр (2026-11-03)
- Миграция `0027_review`: `review_cards` (ease/interval/repetitions/lapses/
  due_at/source) и `review_events`.
- SM-2 (again/hard/good/easy), дневной лимит `REVIEW_DAILY_LIMIT=20`;
  очередь `/review/queue`, ответы, статистика усвоения.
- Автокарточки: failed Python-сабмит и chess-blunder (до 5 за игру);
  дедупликация по `source_ref`; данные в PostgreSQL.
- UI `/review`: карточка, показ ответа, 4 оценки, стрик/удержание.
- Тесты: интервалы/сброс при again, очередь/лимит, дедупликация,
  интеграции Python/chess; backend 190.

#### S-53 — Генератор этюдов v2 (2026-11-03)
- Random-playout + curated-база; batch 1–20 с `exclude_fens`, метриками
  uniqueFens/skipped/defectRate; дедупликация в рамках батча.
- `autoReview` (FEN/легальность PV) в `generator_meta`; сложность по SF
  score; брак → rejected.
- Многоходовый `attempt-line`: проверка PV/префикса, failedPly/nextUci;
  `/admin/studies/generate-batch|generator/metrics`.
- Тесты: 6 уникальных FEN, метрики, полная/неверная линия; backend 192.

#### S-54 — RAG/контент-редактура (2026-11-03)
- Миграция `0028_rag_editor`: `license/status/version/updated_at` +
  `rag_document_versions` (история, created_by).
- Редактор: draft → publish/archive, PATCH (новая версия), rollback;
  retrieval видит только published; версии/лицензии в API.
- Гибридный поиск FTS (`ts_rank_cd`)+vector (0.7/0.3); eval baseline
  vector vs hybrid; импорт `.md/.txt/.pdf` (pypdf, base64).
- Teacher/admin доступ; тесты draft→publish→versions→rollback/import/eval;
  backend 194.

#### S-55 — Нагрузка, доступность и безопасность (2026-11-03)
- `backend/scripts/load_smoke.py`: health p50/p95, concurrency, exit code;
  dev 30/5 → p95 76 мс, readyz ~500 мс; профиль/цели в docs/load-profile.
- A11y: skip-link, `:focus-visible`, aria-label/consent; чеклист в
  docs/a11y-audit (known gaps: aria-live/axe/контраст).
- Security: headers (`nosniff`, frame DENY, referrer, permissions, HSTS prod);
  pip upgrade в Dockerfile; `pip-audit` no known; secrets scan чисто;
  OWASP-ревью в docs/security-review.
- Тест security headers; backend 195.

#### S-56 — Release candidate v0.3.0 (2026-11-03)
- Версии backend/frontend/API → 0.3.0; UI brand v0.3.
- RC acceptance: миграции head 0028, seed/e2e setup; backup+restore
  (sha256/users/alembic) на dev; e2e 7/7; smoke healthz/readyz/SPA; load
  p95 76 мс; backend 195; frontend build; prod compose config OK.
- Live LLM/voice — echo/hash fallback (ключей нет), зафиксировано.
- Runbook `docs/runbooks/release-v0.3.0.md`; known limitations.

## [v0.2.1] — 2026-11-02

### Исправлено
- `docker-compose.prod.yml`: `LLM_EMBED_MODEL` по умолчанию пустой, а не
  несуществующий `nomic-embed-text-v1.5`; приёмка prod выявила лишние
  HTTP 400 и hash-фолбэк. Теперь пустое значение = hash без сетевых вызовов.
- Приёмка v0.2.0 на prod-контуре: миграции 0021, seed, HTTPS, live LLM 4/4,
  классы/аудит/этюды/турниры/экспорт, backup/restore (users=5, 0021).

## [v0.2.0] — 2026-11-02 (16/16 спринтов, этапы E-11…E-16 завершены)

План и DoD — `TODO_V0.2.md` (S-30…S-45). Ниже — история v0.2.0; v0.1.0 — далее.

### Добавлено

#### S-30 — Prod-стек и правда релиза (2026-11-01)
- README / docs/README / CHANGELOG / TODO_V0.1 приведены к факту v0.1.0;
  версии пакетов подняты с `0.1.0.dev0` до `0.1.0`.
- `TODO_V0.2.md` — roadmap S-30…S-45 (E-11…E-16), RULES/README переключены.
- `frontend/Dockerfile` (node 22 → nginx 1.27) + `nginx.conf` (SPA fallback,
  proxy `/api/` и SSE, gzip, cache, security headers), `.dockerignore`.
- `docker-compose.prod.yml`: migrate-гейт, api workers=4 + healthcheck +
  loopback, worker с volume отчётов, web-образ, seed в профиле tools.
- `.env.prod.example`, `scripts/smoke-prod.ps1`; Design §15.1/§15.3 обновлён.
- Фикс worker: `arq.cron("app.worker.scores_recalc")` (был рестарт-луп с S-16);
  регресс-тест `tests/test_worker_settings.py`; prod smoke + heartbeat OK.

#### S-31 — Живой LLM-провайдер и FinOps (2026-11-01)
- RouterAI: слаги сверены с `GET /v1/models` (полные id с префиксами),
  цены ₽/1M обновлены; judge переведён на chat-совместимый
  `google/gemini-3.1-flash-lite` (Decider — decisions-API, не chat).
- `GET /admin/llm/health`: статус `ok|degraded|echo`, доступность всех тиров,
  последний вызов, p95 latency, расход за UTC-день и дневные бюджеты.
- `scripts/llm_smoke.py`: 4 живых маршрута (L1/L2/L3/judge), запись `llm_calls`;
  прогон RouterAI — 4/4 `status=ok`.
- Dev-compose передаёт `.env` в api/worker/migrate/seed; тесты герметичны
  (LLM-сеть отключена в `pytest_configure`).
- Провайдер не возвращает `"None"` при пустом `message.content` — retry/fallback;
  ошибка записи FinOps не повторяет оплаченный вызов; embeddings без модели
  сразу используют hash-фолбэк.

#### S-32 — CodeMirror в редакторах (2026-11-02)
- Deps: `codemirror` 6, `@codemirror/lang-python`, `theme-one-dark`, `state`,
  `view`, `language`.
- `shared/CodeEditor.tsx`: Python-подсветка, номера строк, история, поиск,
  автозакрытие скобок, отступ 4, light/dark (`prefers-color-scheme`), aria-label.
- `shared/LazyCodeEditor.tsx`: CodeMirror в отдельном chunk'е; до загрузки —
  рабочий textarea-fallback.
- Интеграция в PythonPage и BotsPage; черновики в localStorage
  (`cc_draft:python:<id>`, `cc_draft:bots`).
- `npm run build`: tsc 0; main 355.57 kB (gzip 111.93, +1.81 kB), CodeEditor
  lazy-chunk 467.97 kB (gzip 157.16).

#### S-33 — SSE в UI (2026-11-02)
- `shared/useEventStream.ts`: fetch-SSE с Bearer, парсер блоков, reconnect
  с экспоненциальной задержкой и `Last-Event-ID`; Vitest-тесты (5).
- ChessPage: PGN upload → live-прогресс `{ply,total}`, статус, blunders,
  объяснение блюндеров; polling fallback каждые 3 с.
- BotsPage: матч получает реальный `matchId` до enqueue; SSE-прогресс
  `running/done`, polling fallback 2.5 с; лидерборд починен (route order).
- Backend: `match_events` отдаёт начальный статус/позднему подписчику done;
  воркер публикует progress каждые 5 полуходов; chess SSE закрывается на
  done/failed; `domains.auth.models` импортируется в worker-матче (FK users).
- `npm test`: 5 passed; `npm run build`: tsc 0; backend 156 passed.
- CI: job `frontend` (Node 22) — `npm ci` → `npm test` → `npm run build`.

#### S-34 — Доска: drag-and-drop и мобильный UX (2026-11-02)
- Deps: `chess.js` — легальность ходов, FEN, история, undo/redo на клиенте.
- ChessPage: drag-and-drop и click-to-move, подсветка легальных ходов,
  последнего хода и шаха, кнопки undo/redo/сброс/переворот.
- Ввод SAN/UCI (Enter), FEN-apply с валидацией; ошибки хода/FEN.
- Адаптивная вёрстка `.board-controls`, light/dark цвета доски.
- `npm test` 5 passed; `npm run build` tsc 0; main 404.37 kB (gzip 128.44).

#### S-35 — Playwright UI-e2e (2026-11-02)
- Deps: `@playwright/test` 1.64, `pg` (verify-token из dev-БД).
- `playwright.config.ts`: Vite 3201, trace/video retain-on-failure, retries=1,
  один worker; webServer поднимает frontend.
- `e2e/full-journey.spec.ts`: 7/7 passed локально — регистрация (API),
  email verify (БД+API), login UI, задание (CodeMirror), инсайт SF, бот-матч
  через SSE, дашборд, PDF (API).
- CI job `e2e`: pg/redis services, API 8021 + worker, Stockfish, DejaVu,
  Playwright chromium; артефакты trace/video при падении.
- CI backend job: Stockfish + DejaVu + `REPORTS_DIR` — иначе падали
  S-27-тесты на GitHub runner.
- CI run `41357215595`: e2e/backend/frontend зелёные (1m34s/2m32s/12s).
- `npm run test:e2e` — 7 passed (56 с).

#### S-36 — Отдельная e2e-БД и стенд (2026-11-02)
- `docker-compose.e2e.yml`: project `chessclass_e2e`, db 5439, redis 6385,
  api 8021, web 3201; volumes `chessclass_e2e_*`; setup = migrate + seeds.
- `scripts/e2e.ps1` (`up`/`down`/`reset`/`test`/`logs`): `test` делает
  reset → up → Playwright → down -v.
- Изоляция проверена при работающем dev-стеке: 7 passed (15.9 с), dev-БД
  и volumes не затронуты; e2e-стек удалён после прогона.
- CI job `e2e` уже использует отдельные pg/redis services; локальный
  compose-стенд — для параллельной работы с dev.

#### S-37 — Concurrency матчей и справедливость (2026-11-02)
- `domains/bot_lab/queues.py`: `arq:matches:{random,greedy,minimax,sf}`,
  лимиты 2/1/1/1 (суммарно 5), маппинг соперников, ключи active/refused.
- API: max 5 активных матчей на пользователя → 429 `match_limit`;
  enqueue в per-queue arq; `GET /admin/matches/metrics` (p95, timeouts,
  refused, queued/active по очередям).
- Воркеры: `WORKER_QUEUE`/`WORKER_MAX_JOBS` env; compose dev/e2e/prod
  запускает 4 match-воркера; default worker — analyze/pdf.
- `scripts/match_load.py`: 5 матчей (random×2, greedy, minimax2, SF-1400)
  — 5/5 finished за 21.5 с, метрики сняты.
- Тесты: queue mapping/limits, 6-й матч 429, admin metrics; backend 159.

#### S-38 — Бэкапы, TLS и runbook (2026-11-02)
- `backend/scripts/backup.sh`: pg_dump→gzip, sha256, lock, retention 14;
  `scripts/backup.ps1` (custom dump) + `install-backup-task.ps1` + cron.
- `scripts/restore-test.ps1`: sha256, restore в `chessclass_restore`,
  проверка users/alembic, drop; prod-дамп проверен (users=3, 0014).
- `deploy/nginx/edge.conf`: 80→443, TLS 1.2/1.3, HSTS, security headers,
  API/SSE proxy; `gen-self-signed-cert.ps1`; Let's Encrypt — runbook.
- prod compose: `edge` + certbot volume + `ENV_FILE`/`CERTS_DIR`/edge ports;
  smoke-prod проверяет HTTPS/HSTS.
- `docs/runbooks/operations.md`: бэкапы, restore, TLS, секреты, инциденты.

#### S-39 — INSIGHT knowledge для шахмат (2026-11-02)
- `rag/chess.py`: фаза opening/middlegame/endgame по FEN, запрос по
  фазе/теме, лексический rerank поверх hash/embedding-поиска,
  `search_chess_knowledge` (ошибка RAG не ломает insight).
- `db/seeds_rag.py`: +10 chess-документов (дебют, миттельшпиль, эндшпиль,
  король, пешки, расчёт, зевки, оценка, тактика, атака) — 13 всего.
- `chess_lab.insight`/`blunder`: knowledge в промпт и ответ
  (`knowledge[]`), meta позиции; frontend показывает блок «Полезные знания».
- `scripts/chess_rag_eval.py`: 10 текстовых + 3 FEN-проверки — 13/13 OK.
- `LLM_EMBED_MODEL` пуст по умолчанию → hash-фолбэк без сетевых вызовов.
- Тесты: фаза/запрос/поиск + knowledge в insight; backend 162, frontend 5.

#### S-40 — Группы и классы (2026-11-02)
- Миграция `0015_classes`: `classes` (teacher_id, invite_code UNIQUE) +
  `class_members` (PK class_id+user_id), индексы.
- `domains/classes`: 8 endpoints — create/list/join/detail, rotate invite,
  dashboard, add/remove member; RBAC (owner-teacher/admin; student join).
- Dashboard: 11 навыков, флаги (всего/новые), матчи/победы/ничьи/Elo.
- Seed: `teacher@chessclass.dev` (`SEED_TEACHER_PASSWORD`); UI `/classes`:
  список, создание, инвайт, участники, таблица группы.
- Тесты: create/join/dashboard, чужой teacher 403, add/remove/rotate;
  backend 164, frontend 5, build OK.

#### S-41 — Роль auditor и журнал аудита (2026-11-02)
- Миграция `0016_audit`: `users.role` + `auditor`; `audit_logs`
  (actor snapshot, action, target, source, meta, request_id, created_at).
- `domains/audit`: запись в транзакции действия; `GET /admin/audit/logs`
  (фильтры actor/action/target/source/date, пагинация) и
  `GET /admin/audit/export.csv` (UTF-8 BOM, лимит 10 000).
- Auditor read-only: флаги/вердикты/PDF и журнал; review/PDF/классы — 403.
- Логируются действия классов, review флага/вердикта judge, генерация/скачивание
  PDF, экспорт аудита; seed `auditor@chessclass.dev`.
- Фикс `reports_pdfs.requested_by` → nullable (FK SET NULL) — миграция 0017.
- Тесты: auditor read/write, фильтры, CSV, запись действий; backend 165.

#### S-42 — Достижения, стрики и age_group (2026-11-02)
- Миграция `0018_progress`: `py_progress`, `achievements`,
  `user_achievements`, `user_profiles.age_group` (default unknown).
- Стрики: +1 за первый уникальный passed-ассайнмент в новый день; вчера —
  продолжение, пропуск — сброс в 1; повтор задания не считается; лучший
  стрик сохраняется. Хук в `python_teacher.submit`.
- 6 бейджей (seed): first/five/ten solutions, streak_3/7, topics_3;
  `user_achievements` PK гарантирует выдачу один раз; аудит
  `achievements.award`.
- `GET /progress/me` (+ teacher/admin для чужого), UI `/profile`: age_group,
  решено/темы, current/longest streak, каталог бейджей.
- Тесты: стрик/сброс/идемпотентность, age_group, прогресс после сдачи;
  backend 168, frontend 5, build OK.

#### S-43 — Генерация этюдов «код + LLM» (2026-11-02)
- Миграция `0019_studies`: `chess_studies` (FEN/условие/эталон/статус,
  generator_meta, created_by/reviewed_by); индексы.
- Генератор: `STUDY_CANDIDATES` → SF-валидация (легальность, лучший ход/PV)
  → LLM `chess_lab.study` условие; `STUDY_DAILY_LIMIT=10`.
- Поток: draft → submit → review (teacher/admin approve/reject) →
  published; public list/attempt по UCI; брак не публикуется.
- Аудит `studies.generate/submit/review/attempt`; тест 5 этюдов + reject;
  backend 169, frontend 5, build OK.

#### S-44 — Озвучка ответов ElevenLabs (2026-11-02)
- Миграция `0020_voice`: `voice_audio` (text_hash uq, voice/model, path,
  chars, cost, provider); prod volume `chessclass_voice`.
- `domains/voice`: ElevenLabs TTS, кэш по `sha256(voice|model|text)`,
  Redis-квота `VOICE_DAILY_CHARS`, стоимость `VOICE_COST_PER_1K_RUB`,
  аудит `voice.speak`; без ключа — 503 `voice_unavailable`.
- `GET /voice/status`, `POST /voice/speak` → audio/mpeg (+ cached/chars
  headers); UI `VoicePlayer` в инсайте/блюндере/дашборде, текст остаётся
  при 503.
- Тесты: кэш (провайдер вызван один раз), квота, fallback без ключа;
  backend 172, frontend 5, build OK.

#### S-45 — Турниры ботов и экспорт в LMS (2026-11-02)
- Миграция `0021_tournaments`: `tournaments`, `tournament_participants`,
  `tournament_matches`; bracket/round-robin, статусы, ranks/points.
- Турнир без LLM: ходы обоих ботов в песочнице, `TOURNAMENT_MAX_PLIES=40`;
  bracket 8 ботов = 7 матчей, round-robin — все пары; Elo не меняется.
- API: `GET /tournaments`, `GET /tournaments/{id}`, `POST /admin/tournaments`
  (teacher/admin), CSV-экспорт; UI `/tournaments`.
- LMS: `GET /admin/export/skills.csv` (student × skill + progress + Elo),
  `GET /admin/export/xapi` (statements actor/verb/object/result);
  аудит экспортов; UI `/export`.
- Тесты: 8 ботов bracket 7 матчей, CSV/xAPI, 403 для студента; backend 174.

## [v0.1.0] — 2026-11-01 (29/29 спринтов, этапы E-01…E-10 завершены)

Релиз с тегом `v0.1.0` на GitHub (коммит `316fce9`). Все возможности —
в README.md.

### Добавлено

#### S-27 — e2e-набор (2026-11-01)
- `tests/test_e2e_journey.py`: сквозной сценарий §3.4 — регистрация →
  верификация → задание → сдача (passed) → инсайт (реальный SF) →
  бот-матч → навыки/Elo → PDF. CI-стабильность контрактов через API
  (Playwright-UI — полировка).

#### S-26 — Полировка UI (2026-11-01)
- Dashboard: сводка всех доменов (инфраструктура/Elo/слабые навыки),
  инсайт дня (стартовая позиция через шлюз), рекомендации; loading/error
  состояния; dark-тема через prefers-color-scheme.

#### S-25 — PDF-отчёты родителям (2026-11-01)
- Deps: fpdf2>=2.8; DejaVuSans в образе (fonts-dejavu-core) для кириллицы.
- Миграция `0014_reports`: `reports_pdfs` (student/requested_by/kind/path/
  size_bytes).
- `domains/reports/`: build_pdf (навыки + Elo бота), generate_for_student
  (volume + запись), роутер `POST /reports/pdf/{student_id}` (teacher) и
  `GET /reports/pdf/{id}` (скачивание).
- Тесты: сборка с кириллицей, генерация+скачивание, RBAC 403.

#### S-24 — Плагиат и профиль-сверка (2026-11-01)
- `anticheat/similarity.py`: check_plagiarism (hash-эмбеддинги кода,
  косинус ≥0.95 с эталоном/сдачами сверстников; exact-copy = 1.0) и
  check_profile_mismatch (chess ≥70 при python-циклы <40 → флаг, §9.2).
- Плагиат-проверка интегрирована в submit.
- Кабинет учителя: `GET /admin/anticheat/students/{id}/card` — карточка
  ученика (флаги по confidence + judge-сессии).
- Тесты: exact-copy флаг, оригинальное решение чист (false-positive 0),
  карточка (RBAC, 404).

#### S-23 — LLM-judge (Decider) (2026-11-01)
- Миграция `0013_judge_sessions`: `anticheat_judge_sessions` (транскрипт
  JSONB, teacher_verdict/reviewed_by/at).
- `anticheat/judge.py`: start_judge_session (маршрут anticheat.judge_explain,
  question ученика → уточняющие вопросы judge'а; ответ не подсказывает
  решение), list_sessions (teacher/admin), review_session (вердикт).
- API: `POST /admin/anticheat/judge` (student — старт), `GET
  /admin/anticheat/judge?userId` (teacher/admin), `POST .../judge/{id}/verdict`.
- Тесты: старт → транскрипт (system-сообщение) → учительский вердикт
  (student → 403).

#### S-22 — Флаги-движок (2026-11-01)
- `anticheat/likeliness.py`: sf_match_rate (top1/top3 rate + avg accuracy
  против SF) + check_engine_likeliness (порог `ENGINE_LIKELINESS_TOP1_THRESHOLD=0.9`,
  ≥3 семпла) → флаг 0.75.
- Admin-роутер `GET /admin/anticheat/flags?status` (teacher/admin) +
  `POST /flags/{id}/review` (статус-машина: reviewed/false_positive/confirmed).
- Тесты: review-флоу (RBAC 403 student), engine_likeliness против реального
  SF (perfect-bot top1Rate=1.0 → флаг).

#### S-21 — trivial_bot (2026-11-01)
- `bot_lab/trivial.py`: эвристика — захардкоженные UCI-ходы («из кармана»)
  → флаг trivial_bot (0.80; +short_code → 0.90); minimal random-бот валиден
  и не флагается. Порог строк — `BOT_TRIVIAL_MIN_LINES=5`. Запись флага
  при сохранении версии бота. Повторяющийся паттерн — заготовка (mat ≥ 3).

#### S-20 — Elo и матчи UX (2026-11-01)
- `backend/bot_lab/replay.py`: реплей матча (метаданные + ходы) и
  leaderboard (top-10 по Elo, открытым списком — §7.6).
- API: `GET /bots/{id}/matches/{mid}/replay`, `GET /bots/leaderboard`,
  `GET /bots/{id}/matches/{mid}/events` (SSE через pubsub `bots:match:{id}`).
- UI BotsPage: редактор кода бота, тест-ход, матч vs random (polling
  результата), реплей, лидерборд, свой рейтинг.

#### S-19 — Лестница-часть 2: Stockfish UCI_Elo (2026-11-01)
- SF-оппоненты: stockfish-1400/1600/1800 (UCI_LimitStrength + UCI_Elo,
  threads=1, movetime 300 мс, движок-инстанс на матч через EngineService).
- Семплирование ходов ученика 10 % → `bot_match_moves.sf_sample`
  (данные для флага engine_likeliness, E-08).
- `MatchRunIn.pattern` расширен на SF-оппонентов; интеграционные тесты
  против реального SF-1400.

#### S-18 — Матчи и Elo (2026-11-01)
- Миграция `0012_bot_matches`: `bot_stats` (elo/wins/losses/draws),
  `bot_matches` (result CHECK, elo_delta), `bot_match_moves` (реплей).
- `opponents.py`: random ≈400 / greedy ≈800 (материал-дельта) / minimax2
  ≈1100 (negamax глубина 2 + alpha-beta) — trusted-модули воркера.
- `match.py`: матч-луп (MAX_PLIES=60, бюджет 120 с, нарушения ученика =
  поражение), Elo K=32 clamp ±40 (ADR-008), pubsub `bots:match:{id}`;
  arq-задача `run_match`.
- API: `POST /bots/{id}/match/run` (202), `GET /bots/{id}/matches`,
  `GET /bots/stats` (объявлен раньше `/{bot_id}`).

#### S-17 — Боты: контракт и SafePosition (2026-11-01)
- Миграция `0011_bot_versions` (version_no per user, entry, is_active).
- `domains/bot_lab/`: `safe_position.py` (read-only фасад: fen/turn/
  legal_moves/piece_at/is_attacked/material/king_square), `runner.py`
  (собственный subprocess: SafePosition строится в ребёнке, extra_globals
  в run_restricted, per-move таймаут 1.0 с, валидация легальности хода),
  `service.py` (версии/тест), роутер `/api/v1/bots`.
- `chess` добавлен в FORBIDDEN_MODULES песочницы (ботам — SafePosition).
- Тесты: random-бот (легальный UCI), версии, restricted/timeout/contract,
  приватность.

#### S-16 — EMA и дашборд навыков (2026-11-01)
- Миграция `0010_skill_scores`: `user_skill_scores` (PK user+skill,
  week ISO, score 0..100).
- `domains/cognitive/service.py`: recalc_user_scores (EMA α=0.3
  (`SKILL_EMA_ALPHA`), raw = 50 + Σвесов×10, clamp 0..100), scores_snapshot
  (срез 11 навыков), recommendations (skill_links: слабый <40 → связанный
  навык).
- API `/skills`: me / legend / {user_id} (teacher/admin) / recalc.
- arq cron `scores_recalc` nightly (03:40 UTC).
- UI SkillsPage: SVG spider-график 11 навыков, срез, рекомендации.

#### S-15 — Реестр навыков и emits (2026-11-01)
- chess-блюндеры → события навыков (`tactics_hanging`, −1.0, meta gameId/ply)
  в `analyze_game_job`; таблица весов SPEC §8 дополнена.
- (Таблицы skills/skill_events и py-emit'ы — S-03/S-09; judge — E-07.)

#### S-14 — Ассистент E2E (2026-11-01)
- Knowledge-блок в prompt_builder (`build_messages(..., knowledge=...)`):
  RAG-чанки (топ-2, python/general) перед фактами — в
  `python_teacher.hint` и `python_teacher.comment` (по теме задания);
  сбой RAG не ломает ассистента.
- Сквозные тесты сценариев A/B/D (Design §3.4): сдача → вердикт+комментарий
  + llm_calls; позиция → факты+объяснение + llm_calls; RAG-документ →
  knowledge доходит до промпта (echo). Фикстура `worker_role` в conftest.

#### S-13 — RAG: pgvector 768 (2026-11-01)
- Миграция `0009_rag`: `rag_documents` (tsv GIN) + `rag_chunks`
  (embed Vector(768), HNSW vector_cosine_ops).
- `backend/rag/`: embeddings (OpenAI-compat /embeddings + детерминированный
  hash-фолбэк для dev/CI), ingest (чанкинг 800/100, замена по title),
  retrieval (top-k cosine, фильтр доменов), admin-роутер
  `POST /admin/rag/ingest`, `GET /admin/rag/search`.
- Seeds: 7 обучающих документов (python/chess); `scripts/rag_eval.py` (R-04).
- Deps: pgvector>=0.3. Config: LLM_EMBED_MODEL, RAG_CHUNK_CHARS/OVERLAP,
  RAG_TOP_K.

#### S-12 — PGN-анализ и блюндеры (2026-11-01)
- Миграция `0008_chess_games`: `chess_games` (pgn/source), `chess_analyses`
  (status pending→running→done|failed, sf JSONB, llm JSONB).
- `domains/chess_lab`: `ingestion.py` (порт parser'а: PGN → партия,
  валидация), `classifier.py` (Δeval: good/inaccuracy/mistake/blunder,
  порог config CH_BLUNDER_CP=300).
- API: `POST /chess/games/upload` (202, ≤2 МБ), `GET /games/{id}` (статус+
  сводка), `GET /games/{id}/blunders` (с explanation), `POST
  /games/{id}/blunders/explain` (маршрут chess_lab.blunder), `GET
  /games/{id}/events` (SSE прогресс через Redis pubsub).
- arq `analyze_game`: пошаговые eval'ы (профиль analysis: depth 10/150 мс),
  терминальные позиции — из исхода (±9900/0), blunder-детект, pubsub-прогресс.
- Тесты: parse_pgn, валидация/лимиты/приватность.

#### S-11 — Инсайт позиции (2026-11-01)
- Миграция `0007_chess_positions` (upsert по user+fen, meta: facts/factsText/
  explanation/level).
- `POST /chess/insight {fen, level?}`: факты SF (MultiPV + материал) —
  отдельно от LLM-объяснения («LLM не правит факты»); override уровня
  (§4.2); invalid FEN → 422. Исполнение: worker — напрямую, api — arq
  (`analyze_position`, ожидание ≤30 с; `task_timeout`/`task_busy`).
- arq-задача `analyze_position` в воркере (APP_ROLE=worker); очередь
  унифицирована (`arq:queue`).
- Фронтенд: ChessPage — react-chessboard 5 (Chessboard options), панель
  фактов, селектор уровня объяснения, список последних позиций;
  `LoginGate` вынесен в shared.
- Deps: react-chessboard ^5.

#### S-10 — Engine wrapper (2026-11-01)
- `backend/engine/` (порт app/engine annotator, почти verbatim): собственный
  async UCI-клиент (MultiPV-линии, таймауты uciok/readyok/search+4с,
  перезапуск зависшего процесса), профили beginner/club/gm
  (depth 12/18/28, movetime 200/1000/5000), интерактивный clamp ≤1000 мс,
  UCI_Elo (UCI_LimitStrength, 1320..3190), гвард «SF — только worker»
  (APP_ROLE=worker). Модель EngineLine (мат = ±(10000−100·N)).
- Dockerfile: Stockfish 17.1 (ubuntu avx2) ставится в образ на build.
- Deps: chess>=1.10. Config: SF_THREADS/SF_HASH_MB/
  SF_INTERACTIVE_MOVETIME_MS/APP_ROLE.
- Интеграционные тесты против реального SF (skip, если бинарника нет).

#### S-09 — Подсказки, комментарии, low_effort (2026-11-01)
- Миграция `0006_py_hints_cognitive`: `py_reference_solutions` (эталоны),
  `py_feedback` (LLM-комментарий к сдаче), `anticheat_flags` (§9.4:
  kind/domain/source_ref/confidence/evidence/status/review), `cognitive_skill_events`.
- Лестница подсказок §5.4: `POST /py/assignments/{id}/hint` (seeded → LLM
  `python_teacher.hint`), `GET /py/assignments/{id}/solution` (после 3 неудач
  или учителю; `403 solution_locked`); открытия — события с минус-весами.
- Комментарий к сдаче: submit возвращает `feedback` (маршрут comment,
  L1/L2 по уровню ученика, echo в dev); хранится в `py_feedback`.
- Античит-заготовка: low_effort (≤3 строк / неизменённый starter при повторе)
  → флаг с confidence + evidence; не блокирует сдачу (ADR-005).
- События навыков: submit passed +1.0 / failed +0.3; записываются только student'у.
- Seeds: +16 эталонных решений (backfill для существующих заданий).

#### S-08 — Задания и сдача (2026-11-01)
- Миграция `0005_py_domain`: `py_assignments` (slug uq, topic→навык, tests
  JSONB assert-стиль), `py_hints` (лестница: concept/strategy/pseudocode/code),
  `py_submissions` (verdict CHECK: passed/failed/timeout/restricted/error).
- `domains/python_teacher/`: grader (батч-прогон «решение + assert-тесты»
  в песочнице, маркеры с per-run солью — подделка PASS невозможна), сервис
  (CRUD admin, сдача, приватность сдач), роутер `/api/v1/py`.
- Seeds: 16 заданий по темам §5.2 + 18 ступеней подсказок.
- Фронтенд: экран Python-курса — вход (dev), список заданий, редактор кода,
  кнопка «Проверить», вердикт-панель; token-логика в `shared/api.ts`.
- `PageOut` (пагинация) перенесён в `core/base` (общий контракт).

#### S-07 — Песочница (2026-11-01)
- `backend/sandbox/`: `runtime.py` (RestrictedPython 8.5: AST-анализ,
  safe_builtins/гварды, белый список импортов, дружелюбный RestrictedFeatureError),
  `limits.py` (RLIMIT_AS / Windows Job Object, обрезка вывода 64 КБ),
  `executor.py` (subprocess-раннер с per-run timeout, async-обёртка).
- Тест-матрица атак `tests/sandbox/`: os/subprocess/socket/threading/ctypes,
  eval/exec/compile/open, dunder, recursion, memory spike, timeout, обрезка,
  stdin. Dependency: RestrictedPython>=8.5. Config: SANDBOX_*.

#### S-04 — LLM Gateway core (2026-10-31)
- Пакет `backend/llm/`: `base.py` (порт контракта провайдера из teacher),
  `client.py` (OpenAI-совместимый httpx: таймаут 40 с, 1 retry/2 с,
  инъекция транспорта для тестов), `models_registry.py` (5 тиров, цены
  ₽/1M Numeric из env), `routes.py` (10 маршрутов §8.2 с advanced-тирами),
  `gateway.py` (generate по маршруту+уровню), `bootstrap.py` (сверка слагов
  с провайдером, R-01), `router.py` (`GET /api/v1/admin/models`, admin-only).
- Дефолтные слаги моделей (minimax-m3.1 / deepseek-v4.1 / beam-1.0-501b /
  claude-sonnet-5.5 / decider-flash-v1.2) — переопределяются env.
- Тесты: клиент (mock-транспорт: success/retry/unavailable/list_models),
  маршруты (резолв по уровням), шлюз (route→tier→текст), бутстрап-валидация,
  admin-эндпоинт (403 для student).

#### S-03 — Профиль, уровни, RBAC + seeds (2026-10-31)
- `user_profiles` (1:1 с users): display_name, level, billing_tier, prefs
  (миграция `0003_profile_skills`, backfill профилей легаси-юзерам).
- Единый уровень `novice | intermediate | advanced` + маппинг доменных уровней
  (python/chess — ADR-002, `core/levels.py`), `resolve_level` для override на запрос.
- API `/api/v1/profile`: `GET/PATCH /me`, `GET /students` (teacher/admin,
  пагинация), `GET /{id}` (teacher/admin), `PATCH /{id}/level` (admin).
- Уровень профиля попадает в JWT-клейм `level` (login/refresh).
- `skills` + `skill_links`: реестр 11 навыков, 5 кросс-доменных связей (§10.4).
- Seeds (`python -m db.seeds`, compose-сервис `seed`): админ, 2 демо-ученика,
  навыки/связи; идемпотентно.
- `GET /readyz`: ревизия alembic vs head, версия приложения.
- CI: GitHub Actions (ruff, mypy, alembic, seeds, pytest на pg+redis) +
  локальный `scripts/ci.ps1`.

#### S-02 — Аутентификация (2026-10-31)
- Миграция `0002_auth_domain`: `users`, `email_tokens`, `refresh_sessions`.
- `core/security.py`: Argon2id (параметры из config), HS256 access-JWT
  (sub/role/level/type/exp/iat/jti), `parse_duration`.
- `core/ratelimit.py`: fixed-window rate-limit + auth-lockout 5/мин/IP → 10 мин.
- API `/api/v1/auth`: register, verify, login, refresh (ротация), logout, me,
  password-reset (+confirm). Refresh — opaque-токен, в БД только SHA-256,
  HttpOnly-cookie `cc_refresh` (path `/api/v1/auth`); reuse отозванного →
  отзыв всех сессий.
- Email-верификация: одноразовый токен 24 ч; dev — консольный SMTP-бэкенд.
- Домен `domains/auth/`: models / schemas (camelCase) / service / deps
  (`get_current_user`, `require_role` — порт teacher).
- Тесты: юнит security + e2e auth-флоу (ротация, reuse, lockout, password-reset).

#### S-01 — Скелет монорепозитория и инфраструктура (2026-10-31)
- `docker-compose.dev.yml`: `chessclass-db` (pgvector/pgvector:pg17, :5438),
  `chessclass-redis` (:6384), `chessclass-api` (:8020), `chessclass-worker`
  (arq), `chessclass-web` (Vite, :3200), профиль `tools` → `migrate`/`seed`;
  сеть `chessclass-net`, volumes с явными именами (ADR-013, KI-001).
- Backend-каркас: `core/` (config, JSON-логи + request_id, RFC 7807-хендлеры,
  CamelModel, async engine/session, redis-фабрика); `app/main.py` (lifespan,
  CORS, request-id middleware); `GET /healthz` (DB+Redis, никогда не 5xx).
- Alembic (async/asyncpg) + миграция `0001_initial_infra`
  (uuid-ossp, pgcrypto, vector).
- Frontend-каркас: Vite + React 19 + TS, роуты-заглушки, `shared/api.ts`
  (RFC 7807-aware), health-виджет на дашборде, proxy `/api`.
- Документация: `docs/SPEC.md`, `docs/RULES.md`, `.env.example`, `.gitignore`.

## Статусы версий

- **v0.1.0** — выпущен 2026-11-01 (тег `v0.1.0`, 29/29 спринтов).
- **v0.2.0** — выпущен 2026-11-02 (16/16 спринтов).
- **v0.2.1** — выпущен 2026-11-02.
- **v0.3.0** — выпущен 2026-11-03 (12/12 спринтов).
- **v0.4.0** — выпущен 2026-11-04 (12/12 спринтов S-58…S-69).
