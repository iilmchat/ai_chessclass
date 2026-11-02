# CHANGELOG — ChessClass

Формат — по мотивам [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/);
версии соответствуют этапам дорожной карты (`TODO_V0.1.md` — архив,
`TODO_V0.2.md` — активный план). Детали спринтов — в `docs/sprint-reports/`.

## [Unreleased] — v0.3.0

### Добавлено

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
- **v0.2.0** — планируется; активный план — `TODO_V0.2.md`.
