# CHANGELOG — ChessClass

Формат — по мотивам [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/);
версии соответствуют этапам дорожной карты (TODO_V0.1.md). Детали спринтов —
в `docs/sprint-reports/`.

## [Unreleased] — v0.1.0 (этап E-01…E-10, 29 спринтов)

### Добавлено

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

- **v0.1.0.dev0** — активная разработка (этап E-01 «Фундамент» завершается).
