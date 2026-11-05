# SPEC.md — Контракты ChessClass

> **Назначение.** Живой справочник контрактных поверхностей: HTTP API v1,
> DTO, ошибки, события, промпт-таблицы и веса.
> Фундамент решений — `Design.md` (§12 API, §6/§7/§8 домены);
> здесь — только «что видно снаружи» и точные форматы.
> Не хватает факта → сначала добавить в Design, потом сюда.

## 1. Общие конвенции API v1

База всех роутов: `/api/v1`. Правила (обоснование — Design §12.1):

| Аспект | Контракт |
|---|---|
| Имена полей | camelCase (Pydantic `CamelModel` ↔ TS-интерфейсы) |
| Идентификаторы | целые числа как строки (JS-safe), timestamps — ISO 8601 UTC |
| Ошибки | RFC 7807, `application/problem+json`, поле `code` — машиночитаемый слаг |
| CORS | только origin фронтенда (dev: `localhost:3200`, `localhost:3201`) |
| Пагинация | `page` + `pageSize`; ответ `items[]` + `total` (с S-03) |
| Трассировка | каждый ответ несёт `x-request-id`; логи — JSON (Design §16.2) |

## 2. Сводная таблица эндпоинтов

Статусы: 🧱 — запланировано (спринт), ✅ — контракт закреплён и реализован.

| Домен | Route | Метод | Статус | Заметки |
|---|---|---|---|---|
| infra | `/healthz` (дублируется с корня `/`) | GET | ✅ S-01 | `HealthDto{status, db, redis}`; ping БД и Redis, сам никогда не 5xx |
| infra | `/readyz` (дублируется с корня `/`) | GET | ✅ S-03 | ревизия alembic vs head, версия приложения; `status: ready/not-ready` |
| auth | `POST /auth/register`, `/auth/verify`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me`, `POST /auth/password-reset`, `/auth/password-reset/confirm` | — | ✅ S-02 | Argon2id; JWT access 15м; refresh — opaque в БД, HttpOnly-cookie `cc_refresh` (path `/api/v1/auth`), ротация; login требует верифицированный email (Design §13.1) |
| profile | `GET /profile/me`, `PATCH /profile/me`, `GET /profile/students`, `GET /profile/{id}`, `PATCH /profile/{id}/level` | — | ✅ S-03 | RBAC: свой профиль — все; список/чужой — teacher/admin; смена уровня — admin (Design §12.2); пагинация `page`+`pageSize` |
| consent | `GET /consent/status`, `POST /consent/request`, `/consent/confirm`, `/consent/revoke` | — | ✅ S-74 | COPPA/GDPR-K: child/teen → одноразовая ссылка (SHA-256, TTL 7 дней), confirm публичный, revoke владельцем; audit; DDL — §6 |
| python | `GET /py/assignments?level`, `GET/POST /py/assignments`, `PATCH /py/assignments/{id}` (admin), `GET /py/assignments/{id}`, `POST /py/assignments/{id}/submit`, `POST /py/assignments/{id}/hint`, `GET /py/assignments/{id}/solution`, `GET /py/submissions/{id}` | — | ✅ S-08/S-09 | assert-тесты в песочнице; вердикты §3.3; ladder §3.4; флаги §8; тесты ученику не отдаём |
| python | `/python/run` (песочница), `/python/lessons`, `/python/submissions` | — | 🧱 S-03…S-05 | контракт песочницы — Design §6, лимиты — ADR-002 |
| chess | `POST /chess/insight`, `GET /chess/positions`, `POST /chess/games/upload` (202), `GET /chess/games/{id}`, `GET /chess/games/{id}/blunders`, `POST /chess/games/{id}/blunders/explain`, `GET /chess/games/{id}/events` (SSE) | — | ✅ S-11/S-12 | факты SF + LLM-объяснение §3.5; партии фоново (arq), blunders §3.6; SF только воркером |
| bots | `GET /bots`, `POST /bots`, `GET /bots/{id}`, `GET /bots/stats`, `POST /bots/{id}/test`, `POST /bots/{id}/match/run` (202/429 `match_limit`; random/greedy/minimax2/SF-1400/1600/1800), `GET /bots/{id}/matches`, `GET /admin/matches/metrics` (admin) | — | ✅ S-17…S-19/S-37 | choose_move §3.9; per-queue матчи 2/1/1/1; Elo K=32 clamp ±40; sf_sample |
| skills | `GET /skills/me`, `GET /skills/legend`, `GET /skills/{user}` (teacher/admin), `POST /skills/{user}/recalc` (teacher/admin) | — | ✅ S-16 | EMA-скоры §8, spider-дашборд, рекомендации skill_links; PDF — E-09 |
| classes | `GET/POST /classes`, `POST /classes/join`, `GET /classes/{id}`, `POST /classes/{id}/invite`, `GET /classes/{id}/dashboard`, `POST/DELETE /classes/{id}/members[/{userId}]` | — | ✅ S-40 | teacher/admin — создание/управление; student — join/свои классы; чужой teacher — 403 (SPEC §3.11) |
| audit | `GET /admin/audit/logs`, `GET /admin/audit/export.csv` | — | ✅ S-41 | read-only журнал: teacher/admin/auditor; CSV + фильтры (SPEC §3.12) |
| progress | `GET /progress/me`, `GET /progress/{user}` (teacher/admin) | — | ✅ S-42 | стрики, темы, бейджи; age_group в профиле (SPEC §3.13) |
| studies | `GET /studies`, `GET /studies/{id}`, `POST /studies/{id}/attempt`; admin: `GET /admin/studies`, `POST /admin/studies/generate`, `POST /admin/studies/{id}/submit`, `POST /admin/studies/{id}/review` | — | ✅ S-43 | генерация SF+LLM, ревью teacher, публикация, попытка решения (SPEC §3.14) |
| voice | `GET /voice/status`, `POST /voice/speak` | — | ✅ S-44 | ElevenLabs TTS, кэш/квота; 503 без ключа — UI остаётся текстовым (SPEC §3.15) |
| tournaments | `GET /tournaments`, `GET /tournaments/{id}`; admin: `POST /admin/tournaments`, `GET /admin/tournaments/{id}/export.csv` | — | ✅ S-45 | bracket/round-robin без LLM, лидерборд, CSV (SPEC §3.16) |
| export | `GET /admin/export/skills.csv`, `GET /admin/export/xapi` | — | ✅ S-45 | LMS: CSV навыков + xAPI statements (SPEC §3.16) |
| observability | `GET /metrics`; admin: `GET /admin/observability/summary|alerts|costs|costs.csv|retention/status`, `POST /admin/observability/retention/run` | — | ✅ S-46 | метрики, стоимость, retention/архив (SPEC §3.17) |
| auth-hardening | `GET /auth/jwks`, `GET /.well-known/jwks.json`; admin: `PATCH /admin/users/{id}/role`, `PATCH /admin/users/{id}/auditor-scope`, `POST /admin/users/{id}/anonymize` | — | ✅ S-47 | RS256/JWKS, auditor scope, PII-анонимизация (SPEC §3.18) |
| tournaments-v2 | `POST /admin/tournaments` (202/queued), `GET /tournaments/{id}/events` (SSE), `POST /admin/tournaments/{id}/cancel`, `GET /tournaments/{id}/matches/{mid}/replay` | — | ✅ S-48 | async arq, replay, cancel/recovery, SF-античит (SPEC §3.19) |
| lms | admin: `GET /admin/lms/status`, `POST /admin/lms/sync`, `GET /admin/lms/deliveries`, `GET /admin/lms/deliveries.csv` | — | ✅ S-49 | xAPI LRS, retry/идемпотентность, журнал (SPEC §3.20) |
| telegram | `GET /telegram/status`, `POST /telegram/link`, `POST /telegram/link-code`, `POST /telegram/confirm`, `DELETE /telegram/link` | — | ✅ S-50 | consent, code/deep-link, outbox, graceful off (SPEC §3.21) |
| pvp | `POST /pvp/rooms`, `POST /pvp/rooms/join`, `POST /pvp/quick-match`, `POST /pvp/rooms/{id}/start`, `GET /pvp/rooms/{id}/events`, replay, leaderboard, `GET/PATCH /admin/pvp/complaints/{id}` (teacher/admin ревью S-65) | ✅ S-51/S-65 | PvP-комнаты, SSE, отдельный Elo, UI `/pvp` + `/complaints` (SPEC §3.22) |
| review | `GET /review/queue`, `POST /review/cards`, `POST /review/cards/{id}/answer`, `GET /review/stats` | — | ✅ S-52 | SM-2, автокарточки ошибок, дневной лимит (SPEC §3.23) |
| studies-v2 | admin `POST /admin/studies/generate-batch`, `GET /admin/studies/generator/metrics`; `POST /studies/{id}/attempt-line` | — | ✅ S-53 | playout/дедуп FEN, PV-solver, авто-ревью (SPEC §3.24) |
| rag-editor | admin `GET/POST/PATCH /admin/rag/documents`, publish/archive/versions/rollback, `POST /admin/rag/import`, `GET /admin/rag/eval` | — | ✅ S-54 | версии/лицензии, hybrid FTS+vector, PDF/MD (SPEC §3.25) |
| rag | `POST /admin/rag/ingest`, `GET /admin/rag/search?q&k` (admin) | — | ✅ S-13 | pgvector 768, HNSW cosine; hash-фолбэк без провайдера; rag_eval |
| anticheat | `GET /admin/anticheat/flags?status`, `POST /admin/anticheat/flags/{id}/review` (teacher/admin) | — | ✅ S-22 | лента флагов, статус-машина new→reviewed/false_positive/confirmed; engine_likeliness §8 |

## 3. Формат фиксации DTO

Каждый домен оформляет свои DTO в разделах ниже (или в специализированных
документах домена) по образцу:

```ts
// S-xx, домен <name>
interface SomeDto {
  id: string;        // целое число как строка
  createdAt: string; // ISO 8601 UTC
}
```

- Схема добавляется, когда контракт фиксируется в ревизии API.
- Добавление необязательного поля не ломает клиентов; ломающее изменение —
  только через решение в Design (мажор/минор номера фиксируются в §7).

### 3.1. auth (S-02, зафиксировано)

```ts
// POST /api/v1/auth/register → 201
interface RegisterOut { id: string; email: string; role: string; emailVerified: boolean }
// POST /api/v1/auth/login → 200 (+ Set-Cookie: cc_refresh, HttpOnly, SameSite=Lax)
interface AuthOut { accessToken: string; tokenType: "Bearer"; user: UserOut }
interface UserOut {
  id: string; email: string; role: string;
  emailVerified: boolean; isActive: boolean; createdAt: string;
}
// POST /api/v1/auth/refresh → 200 (ротация: Set-Cookie обновляется)
interface TokenOut { accessToken: string; tokenType: "Bearer" }
// /auth/verify, /auth/logout, /auth/password-reset(202), /auth/password-reset/confirm
interface MessageOut { ok: boolean }
```

Факты сверх каталога Design §11.2 (зафиксированы реализацией 0002):
`email_tokens`/`refresh_sessions` получили `created_at` (аудит); refresh-cookie
живёт с `path=/api/v1/auth`; повторное использование отозванного refresh
отзывает все сессии пользователя.

### 3.2. profile (S-03, зафиксировано)

```ts
// GET /api/v1/profile/me → 200
interface ProfileOut {
  id: string; email: string; role: "student" | "teacher" | "admin" | "auditor";
  displayName: string | null;
  level: "novice" | "intermediate" | "advanced" | null; // null — только легаси (до backfill 0003)
  billingTier: "free" | "pro" | null;
  ageGroup: "child" | "teen" | "adult" | "unknown"; // S-42, default unknown
  emailVerified: boolean; isActive: boolean;
  prefs: Record<string, unknown>; createdAt: string;
}
// PATCH /profile/me { displayName?, prefs?, ageGroup? } → ProfileOut (level меняет только admin)
// GET /profile/students?page&pageSize → { items: ProfileOut[], total, page, pageSize }
// PATCH /profile/{id}/level { level } → ProfileOut (только admin)
```

Профиль создаётся при регистрации (level `novice`, tier `free`) и всегда
существует у новых пользователей; миграция `0003` backfill-ом закрыла легаси.
Уровень попадает в JWT-клейм `level` при login/refresh. Данные `skills` /
`skill_links` пока без API (модели + seeds; таблицы — Design §11.2,
миграция `0003`) — API реестра появится вместе с дашбордом (E-08).

### 3.3. python_teacher (S-08, зафиксировано)

```ts
// GET /py/assignments → { items, total, page, pageSize }
interface AssignmentDto {
  id: string; slug: string; title: string;
  level: "novice" | "intermediate" | "advanced";
  topic: string;       // slug навыка реестра (§10.1)
  testsCount: number;
}
// GET /py/assignments/{id} — student: tests=null; admin: тесты видны
interface AssignmentDetailDto extends AssignmentDto {
  statement: string; starterCode: string;
  tests: string[] | null; checkpoints: unknown[] | null; isActive: boolean | null;
}
// POST /py/assignments/{id}/submit { code } → вердикт (Design §5.3)
interface SubmissionDto {
  id: string; assignmentId: string;
  verdict: "passed" | "failed" | "timeout" | "restricted" | "error";
  passedTests: number; totalTests: number; failedTest: number | null;
  stdoutDigest: string | null; durationMs: number | null; createdAt: string;
}
```

Тесты — assert-стиль (однострочные строки в JSONB), исполняются в песочнице
вместе с решением: маркеры результата солятся per-run (подделка PASS невозможна).
`verdict` → `restricted` (Security/RestrictedFeature), `timeout` (per-run),
`error` (runtime-ошибка решения), `passed/failed` по числу пройденных тестов.
`stdout_digest` — вывод ученика (без маркеров), обрезан до 2000 символов.
Slug задания — ключ идемпотентных сидов (сверх каталога §11.2); created_at/
updated_at — аудит. Seeds: 16 заданий (§5.2: переменные → алгоритмы) +
18 ступеней подсказок + 16 эталонных решений.

### 3.5. chess_lab: инсайт (S-11, §6.2)

```ts
// POST /chess/insight { fen, level? } → 200
interface InsightOut {
  fen: string; level: string;
  facts: EngineLineDto[];   // факты SF — отдельно, «LLM не правит факты»
  factsText: string[];      // человекочитаемые факты (панель + блок промпта)
  explanation: string;      // текст LLM (маршрут chess_lab.insight, L2/L3)
  modelUsed: string;
  knowledge: string[];      // RAG-фрагменты (domain=chess, S-39)
}
interface EngineLineDto {
  multipv: number; depth: number; scoreCp: number | null;
  mate: number | null; moveUci: string; pv: string[];
}
// GET /chess/positions?limit → свои позиции с meta {facts, factsText, explanation, level}
```

- Override уровня на запрос (`level`), по умолчанию — профиль (§4.2);
  invalid → 422 `invalid_fen` / `invalid_level_override`.
- Исполнение: **SF — только воркер** (§15.3): api-роль уходит в arq
  (`analyze_position`) и ждёт результат (30 с; `task_timeout` 408,
  `task_busy` 409). Уровень → шахматный через маппинг §4.2.
- Хранение: `chess_positions` upsert по `(user_id, fen)` — одна запись,
  meta обновляется (facts/factsText/explanation/level/knowledge).
- **Knowledge (S-39):** `rag/chess.py` строит запрос по FEN (фаза
  opening/middlegame/endgame + тема), top-3 `domain=chess` передаются в
  `build_messages(..., knowledge=...)`; возвращаются в `knowledge[]`.
  Ошибка RAG не ломает insight (warning + пустой блок).

### 3.6. chess_lab: партии и блюндеры (S-12, §6.2)

```ts
// POST /chess/games/upload { pgn } → 202 { gameId, status: "pending" }
// GET /chess/games/{id} → { gameId, status, blunderCount, summary }
// GET /chess/games/{id}/blunders →
interface BlunderDto {
  ply: number; fenBefore: string;
  playedSan: string; playedUci: string;
  bestSan: string; bestUci: string;
  deltaCp: number; classification: string;
  explanation: string | null;   // из LLM-блока, если объяснён
}
// POST /chess/games/{id}/blunders/explain { ply } → { ply, explanation, modelUsed, knowledge[] }
// GET /chess/games/{id}/events → SSE (event: status|progress; done/failed — конец)
```

- PGN ≤ 2 МБ (`pgn_too_large` 422), читается первая партия mainline
  (`invalid_pgn` 422). Анализ — arq `analyze_game`: пошаговые eval'ы
  профилем `analysis` (depth 10/multipv 1/150 мс), терминальные позиции
  (мат/ничья) движком не анализируются — оценка из исхода
  (мат = ±9900, ничья 0).
- Классификация ходов по Δeval (config `CH_BLUNDER_CP=300`):
  best · good <50 · inaccuracy <100 · mistake <300 · blunder ≥300.
- Прогресс — Redis pubsub `chess:progress:{game_id}` → SSE. Приватность
  как у py_submissions (свои/teacher-admin — 404 чужому).

### 3.7. RAG (S-13, §10.6, ADR-006)

```ts
// POST /admin/rag/ingest { titleRu, source?, domain: python|chess|general,
//   kind: explanation|teacher_solution|chess_position|hint, text } → 201
interface IngestOut { documentId: string; chunks: number; embedMode: "openai" | "hash" }
// GET /admin/rag/search?q&k(1..20) → { query, hits: [{ chunkId, documentId,
//   titleRu, text, similarity }] }  // top-k по косинусу (pgvector <=>)
```

- `rag_documents` (tsv GIN для гибридного поиска) + `rag_chunks` (embed
  Vector(768), HNSW vector_cosine_ops).
- Чанкинг: ~`RAG_CHUNK_CHARS=800` симв. с перекрытием 100, разрыв по
  абзацам/пробелам.
- Эмбеддинги: модель `LLM_EMBED_MODEL` (открытый вопрос §18.2) через
  OpenAI-compat /embeddings; **без провайдера — детерминированный
  hash-фолбэк** (bag-of-words, L2), режим фиксируется в `embedMode` —
  пайплайн ingest/retrieval работает в dev/CI end-to-end.
- Оценка качества (R-04): `backend/scripts/rag_eval.py` — запросы →
  топ-хиты по seed-корпусу (ручная интерпретация).

### 3.8. Ассистент E2E (S-14, §3.4 сценарии A/B/D)

- **Knowledge-блок** (§8.6): `build_messages(..., knowledge=[...])` —
  RAG-чанки (топ-2, домены python/general) перед фактами; вставляется в
  `python_teacher.hint` и `python_teacher.comment` (по теме задания).
  Сбой RAG не ломает ассистента (warning + пустой knowledge).
- Сценарии (тесты `tests/test_assistant_e2e.py`):
  - **A**: сдача → вердикт + LLM-комментарий + запись в `llm_calls`
    (route `python_teacher.comment`);
  - **B**: позиция → факты SF + объяснение + запись `llm_calls`
    (route `chess_lab.insight`; в dev — status `echo`);
  - **D**: инжест знания по теме → hint содержит knowledge-блок
    («Полезный материал (база знаний)» доходит до LLM).

### 3.4. Лестница подсказок (S-09, §5.4)

1. **Seeded ступени** (`py_hints`, kind concept/strategy/pseudocode/code) —
   отдаются по `hintIdx` (POST, одна за разом).
2. **LLM-подсказка** — когда seeded исчерпаны: маршрут `python_teacher.hint`
   (L1; L2 для advanced), промпт через prompt_builder (правила уровня не
   дают готовое решение). Ответ не хранится (журнал — llm_calls).
3. **Решение** — `GET /py/assignments/{id}/solution`: student видит эталон
   после **3 неудачных попыток** (`SOLUTION_LOCK_ATTEMPTS`), teacher/admin —
   всегда; иначе `403 solution_locked`.

Каждое открытие — событие навыка (§8, минус-веса). `SubmissionDto.feedback`
— комментарий LLM к сдаче (route `python_teacher.comment`; echo в dev),
хранится в `py_feedback` (уникален на сдачу); комментарий не ломает сдачу.

## 8. Античит и когнитивные события (S-09)

**Принцип ADR-005: только флаги, решает человек.** Флаги не блокируют
ничего и не видны ученику (§9.6).

**`anticheat_flags`** (§9.4): user_id, kind (engine_likeliness · low_effort ·
trivial_bot · unexplained_code · plagiarism_suspected · profile_mismatch),
domain (python/chess/bot/cross), source_ref (например `py_submission:ID`),
confidence 0..1 Numeric(3,2), evidence JSONB, status (new → reviewed/
false_positive/confirmed), reviewed_by/at, note.

**low_effort (§9.2, эвристики)**: содержательных строк ≤ 3 (`tiny_code`,
confidence 0.60) или неизменённый starter при повторной попытке
(`starter_unchanged_repeat`, 0.80); порог строк — config `LOW_EFFORT_MAX_LINES=3`.

**`cognitive_skill_events`** (§10.2): user_id, skill_id (реестр §10.1),
domain, weight Numeric(6,3), meta JSONB, occurred_at. Базовые веса (таблица
полная — здесь; EMA — E-08):

| Событие | Вес |
|---|---|
| сдача passed | **+1.0** |
| сдача failed (попытка) | +0.3 |
| seeded-подсказка открыта | −0.5 |
| LLM-подсказка | −1.0 |
| открытие решения | **−2.0** |
| блюндер в партии (chess) | −1.0 |

Эмитятся только для роли student; навык отсутствует → skip + warning.

### 3.9. bot_lab: контракт ботов (S-17)

```ts
// POST /bots { code, entry? = "choose_move" } → 201 { id, versionNo, entry, isActive }
// GET /bots (свои, активные) · GET /bots/{id}
// POST /bots/{id}/test { fen } →
interface BotTestOut {
  ok: boolean; moveUci: string | null; timeMs: number;
  error: string | null; errorType: string | null; output: string | null;
}
```

- **Контракт бота**: `choose_move(position) -> str` (UCI-ход) — entry
  настраивается; `evaluate(position) -> float` — для greedy-ботов (S-18).
- **SafePosition** — read-only фасад позиции в песочнице: `fen`, `turn`
  (white/black), `legal_moves` (UCI-список), `is_check`,
  `piece_at(square)`, `is_attacked(square)`, `material(color)`,
  `king_square(color)`. Прямой доступ к python-chess ботам запрещён
  (`chess` в FORBIDDEN_MODULES песочницы).
- Версии: `bot_versions` (version_no растёт per user; is_active — рабочая).
- Запуск: свежий процесс песочницы на ход, per-move таймаут
  `BOT_PERMOVE_TIMEOUT_S=1.0`, RLIMIT 256 МБ, ход валидируется родителем
  (легальность). Коды ошибок: `bot_restricted` (статика), `bot_timeout`
  (408), `bot_error` (422: контракт/нелегальный ход).

### 3.10. Матчи и Elo (S-18, §7.2–7.4)

```ts
// POST /bots/{id}/match/run { opponent: "random"|"greedy"|"minimax2" } → 202
//   { matchId, status: "queued" } — строка матча создаётся до enqueue (S-33)
// GET /bots/{id}/matches → [{ id, opponent, result, movesCount, durationMs, eloDelta, ... }]
// GET /bots/stats → { elo, wins, losses, draws }  // старт 1000
```

- Оппоненты (trusted-модули на воркере, python-chess вне песочницы):
  random ≈400 · greedy ≈800 (материал-дельта) · minimax2 ≈1100
  (negamax глубина 2 + alpha-beta) · **stockfish-1400/1600/1800**
  (SF 17, UCI_LimitStrength + UCI_Elo, threads=1, movetime 300 мс,
  движок — инстанс на матч). LLM в матчах — ноль (§7.3).
- **Семплирование ходов ученика** (S-19): 10 % ходов помечается
  `sf_sample=true` в `bot_match_moves` — данные для флага
  `engine_likeliness` (античит 2.0, E-08).
- Матч: MAX_PLIES=60, бюджет `BOT_MATCH_BUDGET_S=120`; ученик — белыми
  (v0.1); нарушение/ошибка/таймаут ученика = немедленное поражение.
- Elo (ADR-008): старт 1000, K=32, clamp ±40 за матч; `bot_stats` —
  elo/wins/losses/draws; `bot_matches` — result/moves_count/duration_ms/
  elo_delta; `bot_match_moves` — реплей (семплирование SF — S-19).
- Прогресс — Redis pubsub `bots:match:{id}` → SSE
  `GET /bots/{id}/matches/{mid}/events`: начальный `{status:"running", ply}`,
  затем `{status:"running", ply}` каждые 5 полуходов и
  `{status:"done", result, eloDelta}`; поздний подписчик получает done сразу.
- **Реплей**: `GET /bots/{id}/matches/{mid}/replay` — метаданные + ходы
  (ply/fen/uci/agent/thinkMs); приватность как у матчей (404 чужому).
- **Лидерборд**: `GET /bots/leaderboard?limit` — top по Elo (v0.1 открытым
  списком; §18.5 UX-вопрос).
- **Очереди (S-37)**: `POST /bots/{id}/match/run` → 202 `{matchId,status}`
  или 429 `match_limit` (max 5 активных на пользователя); матч попадает в
  `arq:matches:{random|greedy|minimax|sf}` (лимиты 2/1/1/1).
- **Метрики (admin)**: `GET /admin/matches/metrics?hours=24` —
  `{hours,total,byOpponent,timeouts,avgDurationMs,p95DurationMs,refused,
  queues[{kind,queue,limit,queued,active,refused}]}`.

**EMA-скоры** (§10.3, S-16): `user_skill_scores` PK (user_id, skill_id),
week `YYYY-Www` (ISO), score 0..100. Формула: raw = clamp(50 + Σвесов×10,
0..100) за неделю; score = α·raw + (1−α)·prev, α = `SKILL_EMA_ALPHA=0.3`.
Ночных пересчёт — arq cron `scores:recalc` (03:40 UTC); ручной —
`POST /skills/{id}/recalc` (teacher/admin). Нейтральный скор = 50.

### 3.11. classes: классы и группы (S-40, §4.1/§10.5)

```ts
// POST /classes { name } → 201 ClassOut          // teacher/admin
// GET /classes → ClassOut[]                       // teacher — свои; student — членство; admin — все
// POST /classes/join { inviteCode } → ClassOut    // student; повторный join идемпотентен
// GET /classes/{id} → ClassDetailOut              // manager/member; roster — только manager
// POST /classes/{id}/invite → ClassOut            // manager; ротация кода
// GET /classes/{id}/dashboard → ClassDashboardOut // manager
// POST /classes/{id}/members { email } → 201 ClassMemberOut // manager
// DELETE /classes/{id}/members/{userId} → 204     // manager

interface ClassOut {
  id: string; name: string; teacherId: string;
  inviteCode: string | null;   // только manager
  memberCount: number; createdAt: string;
}
interface ClassDetailOut extends ClassOut { members: ClassMemberOut[]; }
interface ClassMemberOut {
  userId: string; email: string; displayName: string | null;
  level: string; joinedAt: string;
}
interface ClassDashboardOut {
  classId: string; className: string; memberCount: number;
  members: [{
    userId: string; email: string; displayName: string | null;
    level: string; joinedAt: string;
    skills: { slug: string; titleRu: string; domain: string; score: number; week: string | null }[];
    flagsCount: number; newFlagsCount: number;
    matchesCount: number; wins: number; losses: number; draws: number; elo: number;
  }];
}
```

- DDL: `classes(id, name, teacher_id FK users, invite_code UNIQUE,
  created_at)`; `class_members(class_id FK classes, user_id FK users,
  joined_at, PK(class_id,user_id))`; индексы `ix_classes_teacher`,
  `ix_class_members_user`.
- RBAC: создание/инвайт/добавление/удаление/дашборд — teacher-owner или
  admin; чужой teacher — 403 `class_forbidden`; student не создаёт класс
  (403), join — только student; чужой/несуществующий код — 404.
- Ошибки: `class_not_found`, `class_forbidden`, `class_invite_invalid`,
  `class_student_only`, `class_member_exists` (409), `class_member_role`
  (422), `class_member_not_found`, `class_name_invalid`.
- Дашборд агрегирует `user_skill_scores` (11 навыков), `anticheat_flags`
  (всего/новые), `bot_stats` (матчи/победы/поражения/ничьи/Elo).

### 3.12. audit: журнал и роль auditor (S-41)

```ts
// GET /admin/audit/logs?actorId&action&targetType&source&dateFrom&dateTo&page&pageSize
//   → { items: AuditLogOut[], total, page, pageSize }
// GET /admin/audit/export.csv?... → text/csv (UTF-8 BOM, attachment)
interface AuditLogOut {
  id: string;
  actorId: string | null;
  actorEmail: string | null;
  actorRole: string | null;
  action: string;              // classes.create, anticheat.flag.review, ...
  targetType: string | null;
  targetId: string | null;
  source: string;              // api | system
  meta: Record<string, unknown>;
  requestId: string | null;
  createdAt: string;
}
```

- Роль `auditor` — read-only: читает флаги/вердикты/PDF и журнал; любые
  мутации → 403 `auth_forbidden`.
- Записываются: `classes.create/join/invite.rotate/member.add/remove`,
  `anticheat.flag.review`, `anticheat.judge.verdict`,
  `reports.pdf.generate/download`, `audit.export`.
- DDL: `audit_logs(id, actor_id FK users SET NULL, actor_email/role — снимок,
  action, target_type/id, source, meta jsonb, request_id, created_at)`;
  индексы actor/created/action. Запись — в той же транзакции, что действие.
- CSV: фильтры те же, лимит 10 000 строк; экспорт сам логируется.

### 3.13. progress: стрики, темы и достижения (S-42)

```ts
// GET /progress/me → ProgressOut
// GET /progress/{user_id} → ProgressOut (teacher/admin)
interface ProgressOut {
  userId: string;
  solvedCount: number;
  topics: Record<string, number>;      // topic slug → решено
  currentStreak: number;
  longestStreak: number;
  lastSolvedOn: string | null;         // YYYY-MM-DD
  achievements: [{
    code: string; titleRu: string; description: string; icon: string;
    awarded: boolean; awardedAt: string | null;
  }];
}
```

- Стрик: первый **уникальный** passed-ассайнмент в новый день → +1; если
  последний день был вчера — продолжение, иначе сброс в 1. Повторное
  решение задания стрик/счётчик не меняет; лучший стрик хранится.
- `py_progress`: `solved_count`, `topics jsonb`, `solved_assignments jsonb`,
  `current_streak`, `longest_streak`, `last_solved_on`, `updated_at`.
- `achievements` (каталог seed) + `user_achievements` (PK user+achievement,
  `context jsonb`, `awarded_at`) — бейдж выдаётся ровно один раз.
  Каталог: first/five/ten solutions, streak_3/7, topics_3.
- `age_group` (`child|teen|adult|unknown`, default `unknown`) — только
  самооценка в профиле; без даты рождения; меняет сам пользователь.
- События выдачи пишутся в `audit_logs` (`achievements.award`, source
  `system`); аудит доступен teacher/admin/auditor (S-41).

### 3.14. studies: этюды SF + LLM (S-43)

```ts
// GET /studies?page&pageSize → { items: StudyOut[], total, page, pageSize }
// GET /studies/{id} → StudyOut (только published; иначе 404)
// POST /studies/{id}/attempt { moveUci } → { correct, message, nextUci }
interface StudyOut {
  id: string; title: string; fen: string; conditionText: string;
  theme: string; difficulty: string; status: string; createdAt: string;
}
// admin (teacher/admin; чтение — также auditor):
// GET /admin/studies?status=draft|review|published|rejected&page&pageSize
// POST /admin/studies/generate → 201 StudyAdminOut (draft)
// POST /admin/studies/{id}/submit → StudyAdminOut (draft → review)
// POST /admin/studies/{id}/review { decision: "approve"|"reject", note? }
//   → StudyAdminOut (review → published|rejected)
interface StudyAdminOut extends StudyOut {
  solutionUci: string; solutionLine: string[]; source: string;
  generatorMeta: Record<string, unknown>;
  createdBy: string | null; reviewedBy: string | null;
  reviewedAt: string | null; reviewNote: string | null;
}
```

- Генератор: курируемая позиция-кандидат → SF-валидация (легальность,
  лучший ход/PV; SF только worker) → LLM `chess_lab.study` формулирует
  условие; черновик `draft`. `STUDY_DAILY_LIMIT=10` на пользователя/сутки
  (429 `study_limit`).
- Ревью: автор/teacher отправляет `draft → review`; teacher/admin
  `approve/reject`; публичная лента только `published`; брак не виден.
- Попытка: UCI-ход проверяется на легальность и совпадение с
  `solution_uci`; неверный/нелегальный — `correct=false`/422.
- Аудит: `studies.generate/submit/review/attempt` (S-41). Решение SF не
  меняется LLM; условие не раскрывает ответ.

### 3.15. voice: озвучка ElevenLabs (S-44)

```ts
// GET /voice/status → { configured, provider, modelId, voiceId }
// POST /voice/speak { text: string (1..2000), voiceId? } → audio/mpeg
//   headers: X-Voice-Cached: 0|1, X-Voice-Chars, X-Voice-Id
```

- `VOICE_API_KEY` пуст → 503 `voice_unavailable`; UI показывает текст без
  плеера (graceful fallback), остальные функции не ломаются.
- Кэш: ключ `sha256(voice|model|text)`, файл в `VOICE_CACHE_DIR`, запись
  `voice_audio` (chars/cost/provider); повторный запрос читает файл и не
  вызывает провайдера.
- Квота: Redis `voice:chars:{user}:{UTC-date}` ≤ `VOICE_DAILY_CHARS`
  (429 `voice_quota`); стоимость — `VOICE_COST_PER_1K_RUB` (Numeric).
- Провайдер: `POST {VOICE_BASE_URL}/v1/text-to-speech/{voice_id}`,
  `xi-api-key`, `model_id`; таймаут `VOICE_TIMEOUT_S`; ошибка → 502.
- Аудит `voice.speak` (chars/cached); ключ не логируется. Кэш в prod —
  volume `chessclass_voice`.

### 3.16. tournaments / export (S-45)

```ts
// GET /tournaments → TournamentOut[]
// GET /tournaments/{id} → TournamentDetailOut
// POST /admin/tournaments { name, format: "bracket"|"round_robin",
//   botVersionIds: number[2..16] } → 201 TournamentDetailOut (teacher/admin)
interface TournamentOut {
  id: string; name: string; format: string; status: "draft|running|done";
  createdAt: string; startedAt: string | null; finishedAt: string | null;
  meta: Record<string, unknown>;
}
interface TournamentDetailOut extends TournamentOut {
  participants: { botVersionId, userId, email, displayName, seed,
                  wins, losses, draws, points, rank }[];
  matches: { roundNo, matchNo, botAId, botBId, winnerId, result,
             movesCount, durationMs }[];
}
// GET /admin/tournaments/{id}/export.csv → CSV (leaderboard + matches)
// GET /admin/export/skills.csv → CSV (student × skill + progress + Elo)
// GET /admin/export/xapi → { statements: [{actor, verb, object, result, timestamp}] }
```

- Турнир — **без LLM**: ходы обоих ботов в песочнице, `TOURNAMENT_MAX_PLIES`
  (40), бюджет per-move как у матчей; Elo/статистика матчей ботов не
  меняются; bracket — 7 матчей для 8 ботов, round-robin — все пары.
- Безопасность: создание/экспорт — teacher/admin (auditor читает экспорт);
  чужие/неактивные боты → 404; 2–16 уникальных.
- Экспорт CSV: `user × skill` (EMA, week, solved/streak, Elo, W/L/D);
  xAPI — statements с actor mbox, verb (`experienced|achieved`), object
  skill/bot-elo, result score; аудит `export.skills`/`export.xapi`.

### 3.17. observability / retention (S-46)

```ts
// GET /metrics → text/plain (Prometheus); METRICS_TOKEN → Bearer
// GET /admin/observability/summary → SummaryOut (admin/auditor)
// GET /admin/observability/alerts → AlertOut[]
// GET /admin/observability/costs?days=30 → { days, items: CostRowOut[] } (admin)
// GET /admin/observability/costs.csv?days=30 → CSV (admin)
// GET /admin/observability/retention/status → { policies, lastRun }
// POST /admin/observability/retention/run { dryRun? } → RetentionResultOut[]
// GET /admin/observability/failed-jobs?status=failed&limit=50 → FailedJobOut[]
// POST /admin/observability/failed-jobs/{id}/retry → FailedJobOut (admin)
```

- Retention: `audit_logs` 365 дн., `llm_calls` 180, `voice_audio`/`voice_usage`
  30, draft/rejected `chess_studies` 90, `failed_jobs` 90; gzip-JSONL в
  `RETENTION_ARCHIVE_DIR` перед удалением; published studies не удаляются;
  dry-run без записи.
- S-76: retry ставит задачу в arq (для `run_match` — в очередь оппонента),
  строка остаётся со статусом `retried`; алерт `failed_jobs_growth` при
  `failed > OBS_FAILED_JOBS_ALERT_THRESHOLD`; метрика
  `chessclass_failed_jobs`.
- `/metrics`: DB/Redis, глубины очередей, active-матчи, LLM/voice cost/tokens,
  свободный диск, DLQ `chessclass_failed_jobs`; S-77 — HTTP RED
  `chessclass_http_requests_total{method,route,status}` и
  `chessclass_http_request_duration_seconds_{bucket,sum,count}` для p95.
  `METRICS_TOKEN` защищает endpoint; в prod — только внутренний scrape.
- Observability-профиль S-77: OTel Collector `:4317`/`:4318` → Tempo
  (traces) и Prometheus `:8889`; Grafana dashboard uid
  `chessclass-http-traces` (`deploy/observability/`).
- Alerts: DB/Redis down, диск < `OBS_DISK_MIN_FREE_GB`, очередь >
  `OBS_QUEUE_ALERT_DEPTH`, LLM cost > `OBS_LLM_COST_ALERT_RUB`, TLS < 30 дн.
  (если `OBS_TLS_CERT_PATH`), retention не запускался > 2 дней.
- `voice_usage` — фактическое использование (включая cache-hit cost=0);
  cost-per-student = `llm_calls` + `voice_usage`.

### 3.18. auth-hardening: RS256/JWKS, auditor scope, PII (S-47)

```ts
// GET /api/v1/auth/jwks | /.well-known/jwks.json → { keys: [JWK] }
// PATCH /admin/users/{id}/role { role } → UserOut (admin)
// PATCH /admin/users/{id}/auditor-scope { scopes: Record<string, boolean> } → {ok}
// POST /admin/users/{id}/anonymize → {ok}
```

- JWT: `JWT_ALGORITHM=HS256|RS256`; RS256 — `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY`
  или `_PATH`, `JWT_KID`; `JWT_LEGACY_HS256=true` принимает старые HS256
  токены при переходе. JWKS отдаёт публичный ключ.
- Audit: `auth.login.success/failed` (failed — emailHash, без PII),
  `auth.role.change`, `auth.auditor_scope.change`, `auth.user.anonymize`.
- Auditor scope (prefs `auditor_scope`): `flags`, `audit`, `reports`,
  `observability`; admin выставляет; teacher/admin не ограничены.
- PII: `age_group` — только самооценка/teacher; анонимизация меняет
  email/пароль/display_name/age_group, деактивирует и отзывает refresh;
  исходные учебные записи сохраняются для аудита.
- Security: decode допускает только настроенный alg + legacy HS256; `none`/
  HS512/подмена подписи → 401; refresh reuse отзывает все сессии.

### 3.19. tournaments-v2: async/SSE/replay (S-48)

```ts
// POST /admin/tournaments {name, format, botVersionIds} → 202 TournamentOut
//   status=queued; job arq `run_tournament_job`
// GET /tournaments/{id}/events → SSE status/progress (running/done/cancelled/failed)
// POST /admin/tournaments/{id}/cancel → TournamentOut
// GET /tournaments/{id}/matches/{matchId}/replay → { match, moves[] }
```

- `tournaments`: `progress`, `total_matches`, `job_id`, `cancel_requested`,
  `error`; статусы `queued|running|done|cancelled|failed`.
- `tournament_moves`: ply/fen/uci/agent (`a|b`)/bot_version_id/think_ms/
  sf_sample; replay и античит.
- Recovery: cron/startup `resume_tournaments` перезапускает queued/running
  с `_job_id=tournament:{id}`; завершённые матчи не дублируются.
- Античит: 10 % ходов помечаются `sf_sample`; после турнира SF-семплы
  проверяются на top-1 rate; флаг `engine_likeliness` (domain=bot).
- Лимит: 2–16 уникальных активных ботов; отмена — между матчами.

### 3.20. LMS LRS (S-49)

```ts
// GET /admin/lms/status → { configured, endpoint, counts, lastDelivery }
// POST /admin/lms/sync → { queued, sent, failed, pending, disabled }
// GET /admin/lms/deliveries?status&limit → DeliveryOut[]
// GET /admin/lms/deliveries.csv?status → CSV
```

- xAPI statements: actor mbox, verb experienced/achieved, object skill/bot-elo,
  result score; `statement_id` — UUID5(actor|object|day) → идемпотентность.
- `lrs_deliveries`: payload/status/attempts/response_status/next_attempt_at;
  retry с экспоненциальным backoff (до 1 ч); `sent` не отправляется повторно.
- `LRS_ENABLED/ENDPOINT/KEY/SECRET`; без конфигурации — только локальный
  CSV, `disabled=1`; worker `lms_sync` каждые 15 мин/на старте.
- Mapping: `https://chessclass.local/skills/{slug}` и
  `https://chessclass.local/bots/{userId}`; LMS-курсы — внешний адаптер.

### 3.21. Telegram-уведомления (S-50)

```ts
// GET /telegram/status → { linked, consent, configured, counts }
// POST /telegram/link { chatId, consent } → { linked, consent, configured }
// POST /telegram/link-code → { code, deepLink, expiresInS }
// POST /telegram/confirm { code, chatId } → { linked, consent, configured }
// DELETE /telegram/link → { linked: false, consent: false, configured }
```

- `telegram_links`: user_id PK, chat_id unique, consent; consent обязателен
  (422 `telegram_consent_required`), отписка удаляет привязку.
- `telegram_outbox`: kind/text/status/attempts/next_attempt_at/sent_at;
  retry/backoff до 1 ч; worker `telegram_deliver` minute=2/startup.
- Код привязки — Redis TTL 600 с, deep link `t.me/chessclass_bot?start=...`;
  rate-limit link/code 5/мин, уведомления 20/сутки на пользователя.
- `TELEGRAM_BOT_TOKEN/API_BASE/LINK_TTL_S/BATCH`; без токена — `disabled=1`,
  отправка не вызывается; токен не логируется.
- Интеграции: бейдж (progress), готовый PDF (reports); `streak`/`review` —
  через `enqueue(kind=...)`.

### 3.22. PvP-матчи ботов (S-51)

```ts
// POST /pvp/rooms { botVersionId, rated? } → RoomOut (201)
// POST /pvp/rooms/join { code, botVersionId } → RoomOut
// POST /pvp/quick-match { botVersionId } → { room, matched }
// POST /pvp/rooms/{id}/start → RoomOut (202/queued tournament)
// GET  /pvp/rooms/{id}/events (SSE), /rooms/{id}/replay?matchId
// GET  /pvp/leaderboard → [{ userId, elo, wins, losses, draws }]
// POST /pvp/rooms/{id}/complaints { reason }; admin GET /admin/pvp/complaints
```

- `pvp_rooms`: code unique, host/guest + bot ids, waiting/ready/running/done/
  cancelled/failed, rated, tournament_id; один активный room на пользователя.
- quick-match ищет waiting-комнату с |ΔElo| ≤ 300, иначе создаёт; лимит
  10 комнат/quick в минуту → 429.
- start создаёт bracket-турнир из двух активных ботов и enqueue
  `run_tournament_job`; SSE/replay — через турнирный канал/`tournament_moves`.
- `pvp_ratings` — отдельно от `bot_stats` (лестница), Elo K=24, 1000 старт;
  финализация после турнира обновляет рейтинг/статистику комнаты.
- Жалобы участников `pvp_complaints` (open/reviewed/rejected); античит
  наследуется из tournament SF-семплов.
- Workflow жалоб (S-65): `PATCH /admin/pvp/complaints/{id}` (teacher/admin)
  — open → reviewed|rejected, note + reviewed_by/at; ревью-очередь UI
  `/complaints`; жалоба отправляется участником из `/pvp`.

### 3.23. Spaced repetition (S-52)

```ts
// GET /review/queue?limit → { cards, dueCount, dailyLimit }
// POST /review/cards { front, back } → CardOut (201)
// POST /review/cards/{id}/answer { rating: again|hard|good|easy } → CardOut
// GET /review/stats → { total, due, reviewsToday, retention, dailyLimit, sm2 }
```

- `review_cards`: source_type manual|python|chess, source_ref unique в рамках
  пользователя; ease/interval_days/repetitions/lapses/due_at.
- SM-2: again → interval 1, repetitions 0, lapses+1; good → 1/6/interval*ease;
  ease ≥ 1.3; `review_events` хранит качество/интервалы.
- Дневной лимит `REVIEW_DAILY_LIMIT` (20); очередь — due_at ≤ now, порядок
  due_at/id; данные в PostgreSQL, переживают рестарт.
- Автокарточки: failed Python-сабмит (source_ref `py:{assignmentId}`) и
  chess-blunder (до 5, `chess:{gameId}:{ply}`), дедупликация.
- UI `/review`: front/back, 4 оценки, статистика; напоминания — через
  Telegram outbox (kind review) при наличии привязки.

### 3.24. Генератор этюдов v2 (S-53)

```ts
// POST /admin/studies/generate-batch { count: 1..20 } → BatchOut
// GET  /admin/studies/generator/metrics → generated/autoReviewed/defects/...
// POST /studies/{id}/attempt-line { moves: string[] } → AttemptLineOut
```

- Кандидаты: curated-база + random-playout из начальной позиции; batch
  передаёт `exclude_fens`, поэтому 20 этюдов без дублей FEN.
- Auto-review: FEN/легальность solution_uci и PV; результат в
  `generator_meta.autoReview`; invalid → `rejected`; брак < 20 %.
- Сложность: по `score_cp` SF (≥250 novice, ≥80 intermediate, иначе
  advanced), `engineDifficulty` в meta.
- `attempt-line` проверяет линию/префикс PV, возвращает failedPly/nextUci;
  `attempt` (первый ход) сохранён для обратной совместимости.
- Batch-лимит 1–20 + общий `study_daily_limit`; метрики — generated,
  autoReviewed, defects, defectRate, duplicateFens.

### 3.25. RAG/контент-редактура (S-54, UI S-64)

```ts
// GET/POST /admin/rag/documents; PATCH /admin/rag/documents/{id}
// POST /admin/rag/documents/{id}/publish|archive|rollback/{version}
// GET  /admin/rag/documents/{id}/versions
// POST /admin/rag/import { filename, contentBase64, license, ... }
// GET  /admin/rag/eval → { baseline, hybrid, passed, cases,
//                          results: [{ order, query, expected,
//                                      vectorHit, hybridHit }] (S-64) }
```

- `rag_documents`: license/status (draft|published|archived)/version;
  `rag_document_versions` — история, created_by; retrieval только published.
- Редактор teacher/admin: create draft, publish/archive, update → new version,
  rollback → восстановление + новая версия; чанки/эмбеддинги пересоздаются.
- Гибрид: 0.7×cosine + 0.3×`ts_rank_cd` (russian), domains/status фильтры;
  `mode=vector` — baseline для eval.
- Импорт: `.md/.markdown/.txt/.pdf` (pypdf) через base64; source=filename,
  license сохраняется.
- Eval (S-64): **gold-set 21 кейс** (`rag/eval_cases.py`, подстроки от
  сид-корпуса 17 доков; `scripts/rag_gold_check.py` — «все подстроки в
  corpus»), сравнение vector/hybrid по каждому кейсу (results-таблица);
  passed = hybrid ≥ baseline. UI `/rag` (teacher/admin): список/фильтры
  статусов, редактор (правка → новая версия), versions+rollback,
  импорт файлом (base64), поиск-превью, eval-панель.

### 3.26. Качество, нагрузка и безопасность (S-55)

- `backend/scripts/load_smoke.py`: p50/p95 health под concurrency; dev
  30/5 → p95 76 мс; `/readyz` ~500 мс (DB/Redis); цели в docs/load-profile.
- A11y: skip-link, `:focus-visible`, aria-label/consent; чеклист
  docs/a11y-audit; axe/aria-live — известные gaps.
- Security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options:
  DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, HSTS prod.
- `pip-audit` (после upgrade pip) — no known; secrets scan tracked files —
  чисто; OWASP-чеклист docs/security-review; critical/high нет.

### 3.27. Release candidate v0.3.0 (S-56)

- Версии: backend/frontend/API 0.3.0; UI brand v0.3.
- Acceptance: migrations head `0028_rag_editor`; backup/restore (sha256,
  users, alembic); e2e 7/7; smoke healthz/readyz/SPA; load p95 76 мс;
  backend 195; frontend build; prod compose config.
- Live LLM/voice — echo/hash fallback (ключей нет); known limitations:
  Telegram/LRS off без токена/endpoint, PvP/RAG UI API-only, CSP/axe/hash-lock.
- Runbook: `docs/runbooks/release-v0.3.0.md`; отчёт S-56.

### 3.28. Релиз v0.3.0 (S-57)
- Тег `v0.3.0` (annotated), GitHub Release с release-notes; CI
  backend/frontend/e2e зелёный.
- Demo-обход: ученик → учитель → родитель → auditor → admin (e2e/тесты/API);
  известные ограничения — в release-notes.
- Backlog v0.4: LMS mapping/LRS OAuth2, Telegram webhook, PvP UI, RAG eval/OCR,
  CSP/egress, hash-lock, axe, staging load, live LLM/voice.

### 3.29. Security: CSP и egress-allowlist (S-61)
**CSP (frontend-nginx).** Политика одна — излучается web-nginx (`frontend/
nginx.conf`), edge её не дублирует (заголовок проходит сквозь; в `location /`
edge нет своего CSP):

```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
img-src 'self' data:; font-src 'self' data:; connect-src 'self';
worker-src 'self'; frame-ancestors 'none'; base-uri 'self';
form-action 'self'; object-src 'none'
```

- Режим задаётся env `CSP_MODE` (web-контейнер), обработчик —
  `frontend/docker-entrypoint.d/40-csp.sh` (sed-свод в Report-Only):
  `enforce` (default — prod/e2e) · `report-only` (staging на период аудита,
  compose ставит `CSP_MODE: report-only`); после аудита — enforce.
- `unsafe-inline` для стилей — осознанный допуск (Vite/React растёт
  inline-стилями: react-chessboard и т.п.); скрипты — только self.
- Release-truth тесты: `tests/test_csp_conf.py` (заголовок enforce в образе,
  механизм Report-Only, отсутствие дублей на edge).

**Egress allowlist (backend).** Все исходящие httpx-клиенты (LLM, voice,
Telegram, LRS) проходят через `core/egress.py` — request-hook `make_egress_hook`:

- разрешено: loopback; `ALLOWED_EGRESS_HOSTS` (env comma/JSON, записи `host`
  или `*.host` — только поддомены); хосты настроенных базовых URL
  (`LLM_BASE_URL`/`LLM_LOCAL_BASE_URL`/`VOICE_BASE_URL`/`TELEGRAM_API_BASE`/
  `LRS_ENDPOINT`); extra-хост клиента (его base_url);
- запрещено: любой другой хост → `AppError("egress_blocked", …, 502)` —
  запрос не уходит (SSRF/deep-defense для детского prod);
- тесты: `tests/test_egress.py` (bypass — тот же LLM-клиент на чужой хост
  краснеет; allowlist/wildcard/поддомены).

### 3.30. Supply chain: hash-lock сборка (S-62, security-review A08)

**`backend/requirements.lock`** — сгенерирован из `pyproject.toml`
(`pip-compile --generate-hashes`, pip-tools, базовый образ python:3.12-slim —
тот же, что и prod). 46 пакетов, каждая запись со `--hash=sha256`
(release-truth тест `tests/test_hash_lock.py` валидирует блоки).

**`backend/Dockerfile` (режим сборки):**

1. `pip install --require-hashes -r requirements.lock` — любое расхождение
   hash (пере-залитый пакет) → build падает;
2. сам проект — `pip install --no-deps -e .` (единственный шаг, где
   PEP 517 build-isolation качает setuptools из PyPI без hash — резидуал
   зафиксирован в отчёте S-62, замкнёт S-63/переделка в двуединую сборку);
3. архива Stockfish — `ARG STOCKFISH_SHA256=<hex-64>` вычисляется от
   `stockfish-ubuntu-x86-64-avx2.tar` **до распаковки**; несовпадение →
   build падает (обновление SF — только с новым hash и волевым актом).

**`backend/scripts/pip_audit.sh`** — `pip-audit -r requirements.lock`
(no known vulnerabilities); контракт в CI — шаг backend job (S-63).

**Обновление зависимостей** — только через перегенерацию lock (RULES §6):
ручной `pip install` в dev-машине не меняет факта сборки.

## 9. Engine Stockfish (S-10)

`backend/engine/` (порт app/engine annotator, почти verbatim): свой UCI-клиент
(PV/multipv, жёсткие таймауты + перезапуск при зависании, неблокирующий loop).

**Профили по шахматному уровню** (§4.2 маппинг):

| Уровень | depth | multipv | movetime |
|---|---|---|---|
| beginner (novice) | 12 | 1 | 200 мс |
| club (intermediate) | 18 | 3 | 1000 мс |
| gm (advanced) | 28 | 5 | 5000 мс |

**Бюджеты и правила:**
- интерактивные вызовы: movetime ≤ `SF_INTERACTIVE_MOVETIME_MS=1000`
  (тяжёлые профили — только через воркер-очередь);
- **«SF — только worker»** (§15.3): гвард `APP_ROLE=worker` в
  `EngineService` (api-процесс получить движок не может);
- UCI_Elo (матчи ботов, §8): `UCI_LimitStrength`, диапазон SF 17 —
  1320..3190; лестница использует 1400–1800;
- таймауты: uciok 15 с, readyok 5 с, поиск movetime + 4 с чтения;
  зависший процесс убивается и поднимается заново;
- модель `EngineLine`: multipv/depth/score_cp/mate/move_uci/pv;
  мат — `±(10000 − 100·N)` (мат в 1 → 9900).

Stockfish 17.1 (ubuntu avx2) ставится в образ на build (Dockerfile);
путь — `STOCKFISH_PATH=/usr/local/bin/stockfish`.

## 10. История ревизий контрактов

## 4. Канон ошибок

| `code` | HTTP | Когда |
|---|---|---|
| `validation_error` | 422 | Pydantic-валидация (поля — в `errors[]`) |
| `auth_unauthorized` | 401 | нет/кривой Bearer-токен (S-02) |
| `auth_invalid_token` | 401 | email-токен недействителен/истёк/использован (S-02) |
| `auth_invalid_credentials` | 401 | неверный email или пароль (S-02) |
| `auth_invalid_refresh` | 401 | нет/кривой/отозванный refresh-токен (S-02) |
| `auth_email_not_verified` | 403 | логин до подтверждения email (S-02) |
| `auth_inactive` | 403 | аккаунт деактивирован (S-02) |
| `auth_forbidden` | 403 | не хватает роли (S-02, `require_role`) |
| `auth_email_taken` | 409 | email уже зарегистрирован (S-02) |
| `rate_limited` | 429 | превышен rate-limit бакета (S-02) |
| `auth_locked_out` | 429 | 5 неудачных логинов/мин/IP → lockout 10 мин (S-02) |
| `quota_exceeded` | 429 | исчерпан LLM-бюджет дня (Design §5.4) |
| `sandbox_timeout` | 408 | таймаут кода/хода (ADR-002 и ботовый ADR) |
| `internal_error` | 500 | необработанное исключение |
| `http_404` … | 404/405… | универсальный маппинг Starlette |

Пример ответа `422`:

```json
{
  "type": "about:blank#validation_error",
  "title": "Validation error",
  "status": 422,
  "code": "validation_error",
  "errors": [{ "field": "level", "message": "not a valid enumeration member" }]
}
```

## 5. Живые события (SSE)

- **Chess PGN**: `GET /api/v1/chess/games/{id}/events` — первый
  `event: status` `{status: pending|running|done|failed}`; затем
  `event: progress` `{ply, total, status}` каждые ~5 позиций;
  `done/failed` — конец потока. Поздний подписчик при уже готовом анализе
  получает `status` и поток закрывается.
- **Bot match**: `GET /api/v1/bots/{id}/matches/{mid}/events` — первый
  `event: progress` `{status:"running", ply}` или `{status:"done", result,
  eloDelta}`; далее progress каждые 5 полуходов и финальный done.
- Авторизация — Bearer access-JWT (заголовок `Authorization`), поэтому
  фронтенд использует `fetch`-SSE (`useEventStream`), а не `EventSource`.
- `useEventStream` поддерживает reconnect с экспоненциальной задержкой и
  `Last-Event-ID`; при недоступности SSE UI переходит на polling
  (`GET /chess/games/{id}` / `GET /bots/{id}/matches`).
- Формат SSE-блока — стандартный `event:`/`data:`; сервер закрывает поток
  после `done/failed`.

## 6. LLM-шлюз: маршруты и модели (S-04)

Домены знают только маршрут `<domain>.<op>` и уровень (ADR-004); резолв тира —
`llm/routes.py`, слаги/цены — env + `llm/models_registry.py` (слаги сверяются
с провайдером на бутстрапе, R-01: несуществующий → warning + автопропуск).

### 6.1. Маршруты v0.1 → тир по уровню

| Маршрут | Назначение | novice/intermediate | advanced |
|---|---|---|---|
| `python_teacher.comment` | комментарий решения | L1 | L1 |
| `python_teacher.hint` | подсказка | L1 | **L2** |
| `python_teacher.explain_code` | разбор отправленного кода | L2 | L2 |
| `chess_lab.insight` | инсайт позиции | L2 | **L3** |
| `chess_lab.next_moves` | объяснение топ-3 ходов | L2 | L2 |
| `chess_lab.blunder` | объяснение плохого хода | L2 | L2 |
| `chess_lab.commentary` | комментарий/беседа | L1 | **L2** |
| `chess_lab.study` | условие шахматного этюда | L1 | L1 |
| `bot_lab.coach` | советы по боту (вне матчей) | L2 | L2 |
| `anticheat.judge_explain` | judge-сессия | **judge** | judge |
| `reports.parent_summary` | абзацы PDF-отчёта | L1 | L1 |

### 6.2. Модели и цены (₽/1M, Numeric(12,4))

| Тир | Слаг (default, env `LLM_MODEL_*`) | in | out | Роль |
|---|---|---|---|---|
| L1 | `minimax/minimax-m3.1-flash` | 5.2362 | 20.9449 | комментарии/подсказки (массовые) |
| L2 | `deepseek/deepseek-v4.1-flash` | 5.7598 | 22.1178 | инсайты, разборы, бот-coach |
| L3 | `reflection/beam-1.0-501b-a23b` | 26.1811 | 104.7245 | advanced, сложные разборы |
| L3_alt | `anthropic/claude-sonnet-5.5` | 209.4490 | 1047.2449 | резерв/проверка качества |
| judge | `google/gemini-3.1-flash-lite` | 26.1811 | 157.0867 | античит-judge (chat-совместимый) |

Слаги — полные id из `GET {LLM_BASE_URL}/models`; цены — каталог RouterAI
на 2026-11-01 (₽/1M). RouterAI Decider (`perplexity/pplx-decider-flash-v1.2`)
использует decisions-API, не OpenAI chat, поэтому judge-route S-31 работает
через Gemini Flash Lite; адаптер Decider — отдельная задача.

Параметры вызовов (temperature/max_tokens) — по маршрутам при переносе промптов
доменов (S-05+); карточки промптов живут в коде, здесь — идентификаторы.

### 6.3. API

- `GET /api/v1/admin/models` (admin) — реестр моделей: `{providerConfigured,
  currency, models[{tier, slug, display, role, configured, priceIn, priceOut}]}`;
  цены — строки Numeric (JSON JS-safe).
- `GET /api/v1/admin/finops/usage?days=7` (admin, 1–90) — агрегат по дням:
  `{currency, days[{day, users, tokensIn, tokensOut, costTotal}]}` (§6.4).
- `GET /api/v1/admin/llm/health` (admin, S-31) — живой статус шлюза:
  `{status: ok|degraded|echo, providerConfigured, baseUrl,
  availableModels[≤50], tiers[{tier, slug, available}], missingModels,
  lastCall{at, route, modelUsed, status, latencyMs}, latencyP95Ms,
  today{tokensIn, tokensOut, costTotal}, budgetFreeTokensDay,
  budgetProTokensDay}`. Проверяет `GET /models` с таймаутом 5 с; `echo` —
  без `LLM_BASE_URL`, `degraded` — провайдер недоступен или слаги не найдены.

### 6.4. Экономика (S-05, зафиксировано)

**Fallback-цепочка** (Design §8.4): cloud RouterAI → local LM Studio
(флаг `LLM_LOCAL_FALLBACK`) → echo; local использует отдельный
`LLM_LOCAL_API_KEY` (LM Studio `Require Auth`) и не переиспользует
облачный ключ; в каждом шаге — 1 retry с
экспоненциальным backoff и jitter. Перед шагом — circuit breaker (Redis,
S-70): 5 ошибок за 60 с → OPEN, через 60 с → HALF_OPEN с одним probe.
Причина переключения — `fallback_from`:
`failover:cloud`/`failover:local` (ошибка провайдера) · `failover:cb_open`
(breaker открыт) · `failover:no_config` (провайдер/ключ не настроен) ·
`quota_exhausted` (квота исчерпана) · `quota_downgrade:{tier}`.
`failover:*` — отказ провайдера; `quota_*` — graceful fallback по квоте.

**llm_calls** (журнал, миграция 0004): `user_id` (nullable — system-вызовы),
`route`, `level`, `model_requested`, `model_used` (слаг / `lmstudio` / `echo`),
`fallback_from`, `tokens_in/out`, `cost_in/out` Numeric(12,4) (null, если цена
не задана), `latency_ms`, `status` (`ok | echo | error`), `task_kind`
(`sync | async`), `trace_id` (S-73, nullable), `created_at`. Пустой `message.content` (reasoning-модель
израсходовала бюджет) — retry, затем fallback, а не строка `"None"`.
Запись `llm_calls` идёт после успешной генерации; сбой FinOps-записи не
повторяет уже оплаченный LLM-вызов (S-31).

**Квоты и бюджеты** (Design §8.5): Redis-ключ `quota:{user}:{YYYY-MM-DD}`
(TTL 48 ч), бюджеты free 50 000 / pro 500 000 токенов/день
(`BUDGET_*_TOKENS_DAY`). Проверка перед вызовом; исчерпание → echo
(метка `quota_exhausted`); остаток меньше оценки входа и тир ≠ L1 →
downgrade до L1 (`quota_downgrade:{tier}`). `anticheat.judge_explain`
не расходует квоту (zero-квота); echo не инкрементирует счётчик и не пишет
`usage_daily`. День — UTC.

**usage_daily** (агрегат): PK `(user_id, day)`; `tokens_in/out`,
`cost_total`, `updated_at`; upsert-инкремент на каждый ok-вызов.

**failed_jobs** (DLQ, S-73, миграция 0032): `id`, `job_id` (unique),
`task`, `args` JSONB, `error_type`, `error`, `attempts`, `trace_id`
(nullable), `status` (`failed | retried | ignored`), `failed_at`.
`core.jobs.track_job` делает upsert по `job_id` при исключении задачи;
ошибка DLQ-записи не маскирует исходное исключение.

**parental_consents** (S-74, миграция 0033): `id`, `user_id` (CASCADE),
`token_hash` (unique, SHA-256), `parent_email`, `policy_version`, `status`
(`pending | granted | revoked | expired`), `requested_at`, `confirmed_at`,
`revoked_at`, `expires_at`. Индексы `(user_id, status)`, `expires_at`.
Одноразовая ссылка живёт 7 дней; после подтверждения/отзыва старый токен
недействителен. Контакт родителя и версия политики сохраняются для
доказуемости согласия. S-75: при `SMTP_HOST` письмо уходит через SMTP
(STARTTLS/SSL/auth), иначе — dev-консоль; child/teen без `granted` получает
403 `parental_consent_required` на LLM и PDF-отчёты (admin/auditor export —
по правовому основанию).

### 6.5. Промпты и параметры генерации (S-06)

`llm/prompts/` (порт prompt_builder/levels из teacher): системный промпт
маршрута = роль (ROLE_BY_ROUTE) + `SECURITY_RULES` (S-71) + правила уровня
(§5.5) + формат (markdown, краткие факты отдельно, RU). Сообщения: system →
история (последние 20, обрезка 4000 симв.) → user. User-сообщение структурно
разделено (ADR-018): `<trusted_instructions>` (инструкция backend-а) →
`<trusted_facts>` (факты движка/тестов) → `<untrusted_user_input>` (код/вопрос
ученика) → `<untrusted_rag_context>` (RAG). Недоверенные блоки санитизируются
(`<|im_start|>`, `[INST]`, `<<SYS>>`, role-метки), секретоподобные строки
редактируются (`llm/security.py`). Изменение текста шаблона → коммит с
поднятием `PROMPT_VERSIONS[route]` и тестом.

| Маршрут | temperature | max_tokens | version |
|---|---|---|---|
| `python_teacher.comment` | 0.3 | 400 | 2 |
| `python_teacher.hint` | 0.3 | 300 | 2 |
| `python_teacher.explain_code` | 0.2 | 700 | 2 |
| `chess_lab.insight` | 0.4 | 600 | 2 |
| `chess_lab.next_moves` | 0.3 | 400 | 2 |
| `chess_lab.blunder` | 0.3 | 400 | 2 |
| `chess_lab.commentary` | 0.5 | 500 | 2 |
| `chess_lab.study` | 0.5 | 300 | 2 |
| `bot_lab.coach` | 0.4 | 600 | 2 |
| `anticheat.judge_explain` | 0.1 | 300 | 2 |
| `reports.parent_summary` | 0.3 | 500 | 2 |

Правила уровней: novice — без готового решения (наводящие вопросы, шаги,
синтаксис на отвлечённом примере); intermediate — причины + фрагменты,
мини-упражнение; advanced — терминология, сложность, альтернативы,
полное решение с комментариями. Echo-режим — dev-заглушка тестов LLM
(CI без ключа): prompt-пайплайн проверяется сквозь `llm_generate`.

## 7. Песочница (S-07)

Единственная точка выполнения ученического кода — `sandbox/`
(Design §13.2): API-процесс никогда не `exec`-ит код, каждый запуск —
свежий дочерний интерпретатор.

**Слои защиты:** статический AST-анализ (запрещённые импорты/вызовы/dunder) →
`compile_restricted` (RestrictedPython 8.5) → ограниченные builtins + гварды
доступа/записи → собственный `__import__` с белым списком → subprocess с
лимитами (RLIMIT_AS/Job Object ставится внутри дочернего процесса).

**Разрешённые модули:** math, random, datetime, collections, itertools,
functools, string, re, statistics, decimal, fractions, json.
**Запрещённые вызовы:** eval, exec, compile, open, __import__, globals, locals.
`input()` разрешён — читает только переданный stdin.

**Результат `run_restricted` / executor.run:** `{success, output, error,
error_type, execution_time, violations[], memory_limit_enforced,
output_truncated, limits_warning}`. Коды `error_type`: `SecurityError`
(статика), `SyntaxError`, `RecursionError`, `MemoryError` (RLIMIT_AS),
`TimeoutError` (per-run), `RestrictedFeatureError` (подсказка про
f-строки вместо .format — RP 8.x), `SandboxCrash`.

**Лимиты (config/env):** память `SANDBOX_MEMORY_LIMIT_MB=256`, обрезка вывода
`SANDBOX_MAX_OUTPUT_CHARS=65536` (64 КБ + пометка), таймаут заданий
`SANDBOX_TIMEOUT_S=5`, боты — `BOT_PERMOVE_TIMEOUT_S=1`.

**Тест-матрица атак** (`tests/sandbox/`, обязательный набор §16.1): импорты
(os/subprocess/socket/threading/ctypes), eval/exec/open/compile, dunder-атрибуты,
recursion, memory spike, бесконечный цикл (timeout), обрезка вывода, stdin.

## 8. История ревизий контрактов

| Дата | Изменение | Спринт |
|---|---|---|
| 2026-10-31 | S-01: базовые конвенции v1, `/healthz` ✅ | S-01 |
| 2026-10-31 | S-02: auth-контракты ✅ — 8 эндпоинтов, DTO §3.1, 10 кодов ошибок | S-02 |
| 2026-10-31 | S-03: profile-контракты ✅ — 5 эндпоинтов, DTO §3.2, `/readyz`, пагинация включена | S-03 |
| 2026-10-31 | S-04: LLM-контракты ✅ — 10 маршрутов §6.1, реестр моделей §6.2, `GET /admin/models` | S-04 |
| 2026-10-31 | S-05: экономика ✅ — fallback-цепочка, llm_calls/usage_daily, квоты/бюджеты, FinOps API | S-05 |
| 2026-10-31 | S-06: промпты ✅ — системные шаблоны по уровням, таблица параметров §6.5 | S-06 |
| 2026-11-01 | S-07: песочница ✅ — executor (subprocess, таймаут/RLIMIT), матрица атак; контракты §7 | S-07 |
| 2026-11-01 | S-08: py-домен ✅ — задания/сдача/вердикты, DTO §3.3, seeds 16 заданий | S-08 |
| 2026-11-01 | S-09: ladder/комментарии/low_effort ✅ — §3.4, §8 (флаги, веса событий) | S-09 |
| 2026-11-01 | S-10: Engine ✅ — профили §9, UCI_Elo, SF только worker; SF 17.1 в образе | S-10 |
| 2026-11-01 | S-11: инсайт ✅ — §3.5 (facts+LLM), arq-путь api→worker, chess_positions | S-11 |
| 2026-11-01 | S-12: партии/блюндеры ✅ — §3.6 (upload/arq/SSE/explain), классификация Δeval | S-12 |
| 2026-11-01 | S-13: RAG ✅ — §3.7 (pgvector 768/HNSW, ingest/search, hash-фолбэк) | S-13 |
| 2026-11-01 | S-14: ассистент E2E ✅ — knowledge-блок (RAG) в промптах, сценарии A/B/D | S-14 |
| 2026-11-01 | S-15: emits ✅ — chess-блюндеры → tactics_hanging (−1.0); таблица весов §8 полная | S-15 |
| 2026-11-01 | S-16: EMA/дашборд ✅ — user_skill_scores, /skills API (§8), cron nightly, spider-UI | S-16 |
| 2026-11-01 | S-17: боты-контракт ✅ — §3.9 (SafePosition, choose_move), bot_versions, chess в запретах | S-17 |
| 2026-11-01 | S-18: матчи/Elo ✅ — §3.10 (random/greedy/minimax2, arq-луп, K=32 clamp ±40) | S-18 |
| 2026-11-01 | S-19: SF-лестница ✅ — UCI_Elo 1400/1600/1800, семплирование 10 % (sf_sample) | S-19 |
| 2026-11-01 | S-20: матчи-UX ✅ — replay/leaderboard/SSE, BotsPage (редактор/матч/реплей) | S-20 |
| 2026-11-01 | S-21: trivial_bot ✅ — hardcoded-ходы → флаг (ADR-005: не блокирует) | S-21 |
| 2026-11-01 | S-22: флаги-движок ✅ — engine_likeliness (top1Rate ≥ 0.9 → флаг), review-статус-машина | S-22 |
| 2026-11-01 | S-23: judge ✅ — anticheat.judge-сессии (транскрипт, вердикт учителя) | S-23 |
| 2026-11-01 | S-24: плагиат/сверка ✅ — similarity ≥0.95 → флаг, profile_mismatch, карточка ученика | S-24 |
| 2026-11-01 | S-25: PDF-отчёты ✅ — fpdf2+DejaVuSans (кириллица), reports_pdfs, GET/POST /reports/pdf | S-25 |
| 2026-11-01 | S-26: полировка UI ✅ — дашборд-сводка, статистика Elo, инсайт дня, dark-тема | S-26 |
| 2026-11-01 | S-27: e2e ✅ — полный journey §3.4 (регистрация→...→PDF) в тест-наборе | S-27 |
| 2026-11-01 | S-31: LLM live ✅ — RouterAI-слаги/цены, `/admin/llm/health`, smoke 4/4, FinOps | S-31 |
| 2026-11-02 | S-33: SSE UI ✅ — `useEventStream`, PGN-прогресс/blunders, матч-прогресс, polling fallback | S-33 |
| 2026-11-02 | S-37: match queues ✅ - per-queue workers, max 5 active, metrics/load | S-37 |
| 2026-11-02 | S-38: backups/TLS ✅ - sha256/retention, restore-test, edge HTTPS/HSTS, runbook | S-38 |
| 2026-11-02 | S-39: chess knowledge ✅ - 13 seed-док, FEN/phase/rerank, knowledge в insight/blunder, eval 13/13 | S-39 |
| 2026-11-02 | S-40: classes ✅ - classes/class_members, invites, teacher dashboard, RBAC; UI кабинета | S-40 |
| 2026-11-02 | S-41: audit ✅ - роль auditor (read-only), audit_logs, CSV/фильтры, логирование действий | S-41 |
| 2026-11-02 | S-42: progress ✅ - py_progress/стрики, achievements/бейджи, age_group, UI профиля | S-42 |
| 2026-11-02 | S-43: studies ✅ - SF+LLM генерация, draft→review→published, attempts, лимит/аудит | S-43 |
| 2026-11-02 | S-44: voice ✅ - ElevenLabs TTS, cache/voice_audio, quota, UI-плеер, text fallback | S-44 |
| 2026-11-02 | S-45: tournaments/export ✅ - 8-бот bracket без LLM, CSV/xAPI для LMS, UI | S-45 |
| 2026-11-02 | S-46: observability/retention ✅ - voice_usage, gzip-архив, metrics, alerts, cost/UI | S-46 |
| 2026-11-02 | S-47: auth-hardening ✅ - RS256/JWKS, audit логинов/ролей, auditor scope, PII | S-47 |
| 2026-11-02 | S-48: tournaments-v2 ✅ - async arq/SSE, replay, cancel/recovery, SF-античит | S-48 |
| 2026-11-02 | S-49: LMS LRS ✅ - xAPI queue/retry, scheduled sync, delivery journal/CSV | S-49 |
| 2026-11-03 | S-50: Telegram ✅ - consent/link-code, outbox/retry, graceful off | S-50 |
| 2026-11-03 | S-51: PvP ✅ - rooms/quick-match, SSE/replay, separate Elo | S-51 |
| 2026-11-03 | S-52: review ✅ - SM-2 cards, error integrations, daily cap | S-52 |
| 2026-11-03 | S-53: studies-v2 ✅ - playout/dedup, PV solver, auto-review | S-53 |
| 2026-11-03 | S-54: RAG editor ✅ - versions/license, hybrid FTS, import/eval | S-54 |
| 2026-11-03 | S-55: quality ✅ - load p95, a11y, security headers/audit | S-55 |
| 2026-11-03 | S-56: RC ✅ - migrations/backup/e2e/smoke, versions 0.3.0 | S-56 |
| 2026-11-03 | S-57: release v0.3.0 ✅ - tag/release/demo/backlog | S-57 |
| 2026-11-03 | S-61: CSP/egress ✅ — §3.29 (CSP report-only→enforce, egress-hook 4 клиентов) | S-61 |
| 2026-11-03 | S-62: hash-lock ✅ — §3.30 (requirements.lock 46 пакетов с hash, sha256 Stockfish, pip-audit) | S-62 |
| 2026-11-03 | S-64: RAG-редактор UI ✅ — §3.25 (gold-set 21, results, «/rag» teacher/admin) | S-64 |
