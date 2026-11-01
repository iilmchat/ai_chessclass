# CHANGELOG — ChessClass

Формат — по мотивам [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/);
версии соответствуют этапам дорожной карты (TODO_V0.1.md). Детали спринтов —
в `docs/sprint-reports/`.

## [Unreleased] — v0.1.0 (этап E-01…E-10, 29 спринтов)

### Добавлено

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

- **v0.1.0.dev0** — активная разработка (этап E-01 «Фундамент» завершается).
