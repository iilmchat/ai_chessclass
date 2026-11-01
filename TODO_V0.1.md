# TODO_V0.1.md — Спринты этапа v0.1.0 (ChessClass)

**Статус:** план · **Дата:** 2026-10-31 · **Производная от:** `Design.md` §17 (E-01…E-10)

> **Правила чтения.** Каждый спринт — итерация 2–3 рабочих дня со
> сквозной приёмкой: «можно продать» (демо-полка каждые 2–3 спринта,
> см. Design §17.3). Отчёт спринта — в `docs/sprint-reports/`
> (формат — 7 пунктов, шаблон будет в `docs/RULES.md`).
> Статусы: ☐ не начат · 🔶 в работе · ✅ готов · 🚫 блокер.
> После завершения спринта — отметка факта и ссылка на отчёт.

**Сводно:** 29 спринтов / 10 этапов. Порядок этапов фиксирован зависимостями
(ядро → домены → наслоения → финал); внутри этапа спринты можно менять местами.

---

## E-01 · Фундамент (S-01…S-03)

### S-01 ✅ Скелет монорепозитория и инфраструктура
- [x] структура репо по Design §3.3; `.env.example`, `.gitignore`
- [x] docker-compose.dev.yml: `chessclass-db` (pg 17+pgvector, :5438),
      `chessclass-redis` (:6384), `chessclass-api` (:8020), `chessclass-worker`, `chessclass-web` (:3200)
- [x] backend: FastAPI app, core/config (Pydantic Settings), logging, errors (RFC 7807), db session, redis
- [x] frontend: Vite React 19 + TS каркас, apiClient, маршруты-заглушки
- [x] alembic init; миграция базиса (extensions pgvector/pgcrypto/uuid-ossp)
- [x] `docs/SPEC.md` (шаблон: DDL-раздел) + `docs/RULES.md` (шаблон: 7-пунктовый отчёт)
- **DoD:** `docker compose up` поднимает всё; `GET /healthz` зелёный ✅
  (2026-10-31: `{"status":"ok","db":true,"redis":true}`; отчёт — docs/sprint-reports/S-01-2026-10-31.md)
- **Порт из teacher:** core/config, db, logging (§20.1)

### S-02 ✅ Аутентификация
- [x] `users`, `email_tokens`, `refresh_sessions` (DDL → SPEC)
- [x] Argon2id пароли; регистрация/логин; JWT access (15 м) + refresh HttpOnly (30 д, ротация)
- [x] email-верификация (dev — консольный SMTP), rate-limit auth
- [x] logout/revoke, lockout 5/мин/IP
- **DoD:** e2e-зарегистрироваться → подтвердить email → залогиниться → refresh ✅
  (2026-10-31: pytest 9 passed + curl-демо; отчёт — docs/sprint-reports/S-02-2026-10-31.md)
- **Порт из teacher:** security-модули

### S-03 ✅ Профиль, уровни, RBAC + seeds
- [x] `user_profiles` (level, billing_tier); роли student/teacher/admin + пермишен-зависимости
- [x] единый enum уровня + маппинг уровней (Design §4.2), override `level` на запрос
- [x] seeds: админ, запасные ученики, skills/skill_links (Design §10.1, §10.4)
- [x] `/readyz` детали; CI-продукция: ruff/mypy/pytest
- **DoD:** профиль с ролью; teacher видит учеников; тесты CI зелёные ✅
  (2026-10-31: pytest 19 passed, ruff/mypy 0; отчёт — docs/sprint-reports/S-03-2026-10-31.md)
- **Порт из teacher:** models/уровни (ADR-002, §20.1)

---

## E-02 · LLM-шлюз (S-04…S-06)

### S-04 ✅ Gateway core
- [x] OpenAI-совместимый клиент (httpx), RouterAI env, таймауты/ретраи
- [x] реестр маршрутов `<domain>.<op>`×level (Design §8.2) + карта моделей L1/L2/L3/judge
- [x] проверка слагов моделей на бутстрапе (`/models` роутер), цены ₽/1M (Numeric)
- **DoD:** вызов по маршруту возвращает текст; слаги валидированы логом ✅
  (2026-10-31: pytest 34 passed (mock-транспорт); /admin/models демо; отчёт — docs/sprint-reports/S-04-2026-10-31.md)
- **Порт из teacher:** llm base client, policy

### S-05 ✅ Экономика: llm_calls, бюджеты, fallback
- [x] таблицы `llm_calls`, `usage_daily` (DDL → SPEC); запись tokens/₽/latency
- [x] квоты в Redis, бюджеты free 50k / pro 500k ток/день, graceful downgrade (L1 → echo)
- [x] fallback-цепочка cloud → local (LM Studio, флаг) → echo; retry 1×2с
- **DoD:** FinOps-таблица: llm_calls заполняется; бюджет режет выдачу ✅
  (2026-10-31: pytest 41 passed; журнал в БД + /admin/finops/usage; отчёт — docs/sprint-reports/S-05-2026-10-31.md)
- См. Design §8.4–8.5

### S-06 ✅ Промпты уровня (prompt_builder)
- [x] порт prompt_builder (системные промпты по уровню, RU)
- [x] шаблоны для маршрутов python_teacher/chess_lab (таблица параметров → SPEC)
- [x] echo-режим как dev-заглушка тестов LLM
- **DoD:** маршрут comment/hint/insight выдают промпт по уровню ✅
  (2026-10-31: pytest 50 passed; отчёт — docs/sprint-reports/S-06-2026-10-31.md)

---

## E-03 · Python-домен (S-07…S-09)

### S-07 ✅ Песочница (порт executor)
- [x] RestrictedPython 8.5 executor: белый список импортов, глобалы, лимиты времени/памяти
- [x] per-run timeout; обрезка stdout/stderr (64 КБ); запрет сети/файлов/потоков/os
- [x] тест-матрица атак (import os, eval, recursion, memory, threading) — `tests/sandbox/`
- **DoD:** песочница отбивает тест-матрицу; живой smoke (sum + атака + timeout) ✅
  (2026-11-01: pytest 79 passed; отчёт — docs/sprint-reports/S-07-2026-11-01.md)
- **DoD:** 20+ эксплоитов — все блокируются; порт из teacher проверен
- **Порт из teacher:** sandbox/executor (§20.1) — E-03, E-07

### S-08 ✅ Задания и сдача
- [x] `py_assignments`/`py_submissions`/`py_hints` (DDL → SPEC); Pydantic-роутеры
- [x] тесты assert-стиль (исполняются в executor); вердикт passed/failed/timeout/restricted
- [x] UI экран задания: условие + редактор + тесты (порт виджета, §20.3)
- [x] seed 15–20 заданий (темы Design §5.2: переменные…алгоритмы)
- **DoD:** ученик решает задание и видит вердикт ✅
  (2026-11-01: pytest 90 passed + curl-демо passed 3/3; отчёт — docs/sprint-reports/S-08-2026-11-01.md)

### S-09 ✅ Подсказки, комментарии, low_effort
- [x] hint ladder: seeded → LLM-подсказка → solution (открытие = событие с минус-весом)
- [x] маршруты python_teacher.comment/hint/explain_code (L1/L2 по уровню)
- [x] эвристика low_effort (копипаста/микро-попытки) → запись в anticheat_flags (заготовка)
- **DoD:** сдача → комментарий от LLM по уровню; первый флаг low_effort ✅
  (2026-11-01: pytest 96 passed; feedback echo + флаг 0.60 tiny_code; отчёт — docs/sprint-reports/S-09-2026-11-01.md)
- **Порт из teacher:** llm policy матрица

---

## E-04 · Шахматный домен (S-10…S-12)

### S-10 ✅ Engine wrapper (порт)
- [x] Stockfish 17 UCI-обёртка: bestmove/eval/PV/multipv; UCI_Elo; threads/movetime из env
- [x] бюджет вызовов: интерактив movetime ≤ 1.0 c; «SF — только worker» правило
- [x] интеграционные тесты против реального SF (короткий бюджет)
- **DoD:** SF 17.1 в образе; e2e4 (+37cp, d18), Re8# (mate 1), UCI_Elo 1400 ✅
  (2026-11-01: pytest 104 passed (+8 engine); отчёт — docs/sprint-reports/S-10-2026-11-01.md)
- **Порт из annotator:** engine/ (§20.2) — почти verbatim

### S-11 ✅ Инсайт позиции
- [x] `chess_positions`, UI/бэк: доска (react-chessboard) + панель фактов
- [x] маршрут chess_lab.insight: facts SF → LLM L2 (L3 для advanced), «LLM не правит факты»
- [x] UI переключение уровня объяснения (override)
- **DoD:** ученик получил инсайт с фактами SF + объяснением по уровню ✅
  (2026-11-01: pytest 108 passed; демо Re8# через api→arq→worker; отчёт — docs/sprint-reports/S-11-2026-11-01.md)

### S-12 ✅ PGN-анализ и блюндеры
- [x] upload PGN (≤ 2 МБ) → arq задача analyze: пошаговые eval'ы, детект Δeval ≥ порога
- [x] маршруты chess_lab.blunder / commentary; итоговая сводка партии
- [x] `chess_games`, `chess_analyses` (DDL → SPEC); SSE прогресс разбора
- **DoD:** партия разбирается фоново; blunders в списке с объяснениями ✅
  (2026-11-01: pytest 113 passed; демо Scholar's mate → blunder Nf6 Δ9932; отчёт — docs/sprint-reports/S-12-2026-11-01.md)

---

## E-05 · RAG и сквозной ассистент (S-13…S-14)

### S-13 ✅ pgvector 768 (ingest + retrieval)
- [ ] `rag_documents`, `rag_chunks` (vector(768), HNSW-индекс); маршрут rag.embed в gateway
- [ ] ingest-админка: загрузка текстов/этюдов/решений учителя; чанкинг
- [ ] retrieval: топ-k по косинусу; скрипт `scripts/rag_eval` (качество, R-04)
- **Открытый вопрос перед стартом:** выбор embedding-модели 768 (Design §18.2)
- **DoD:** seed-корпус; поиск выдаёт релевантные фрагменты

### S-14 ✅ Ассистент E2E (сквозной сценарий D)
- [x] вставка RAG-контекста в промпты (блок knowledge, Design §8.6)
- [x] маршруты: хинты/комментарии/инсайты ходят через единый gateway с квотами
- [x] сквозной прогон «A/B/D» (Design §3.4): сдача → комментарий; позиция → инсайт
- **DoD:** ассистент работает от входа до ответа с записью llm_calls ✅
  (2026-11-01: pytest 121 passed — сценарии A/B/D; отчёт — docs/sprint-reports/S-14-2026-11-01.md)

---

## E-06 · События навыков (S-15…S-16)

### S-15 ✅ Реестр навыков и emits
- [x] `skills`, `cognitive_skill_events` (DDL → SPEC); общий emit-хелпер
- [x] интеграция emits: py-сдачи/подсказки/solution, chess-блюндеры, judge
- [x] карта «тема задания → навык» (Design §10.1), веса (таблица → SPEC)
- **DoD:** любая сдача/анализ порождает события навыков ✅
  (2026-11-01: pytest 122 passed; таблицы/emit сделаны в S-03/S-09, доподтянуты
  chess-блюндеры; judge — E-07; отчёт — docs/sprint-reports/S-15-2026-11-01.md)

### S-16 ✅ EMA и дашборд ученика
- [x] `user_skill_scores`: недельные EMA (α в config), задача arq `scores:recalc` (nightly)
- [x] UI `/skills`: spider-график ~11 навыков, тренды, рекомендации по skill_links
- **DoD:** ученик видит прогресс; учителю — срез по ученику ✅
  (2026-11-01: pytest 126 passed; демо /skills/me 11 навыков; отчёт — docs/sprint-reports/S-16-2026-11-01.md)

---

## E-07 · Лаборатория ботов (S-17…S-21)

### S-17 🧪 Контракт и SafePosition
- [ ] SafePosition read-only прокси: fen/turn/legal_moves/piece_at/is_attacked/material
- [ ] запись ботов: контракт `choose_move(position)->str` / `evaluate(position)->float`
- [ ] `bot_versions`; запуск в executor (per-move 1.0 c); запрет импорта python-chess внутрь
- **Порт из teacher:** executor — общий, не копия (§20.4)
- **DoD:** простой random-бот ученика возвращает легальные ходы

### S-18 🎯 Лестница-часть 1: random + greedy + minimax2
- [ ] оппоненты random (≈400), greedy (≈800, по evaluate/материал-дельта)
- [ ] minimax2 (≈1100, negamax глубина 2 + alpha-beta через SafePosition)
- [ ] матч-луп в arq без LLM; MAX_PLIES=60, BOT_MATCH_BUDGET_S=120
- **DoD:** матч против random/greedy/minimax2 играется до конца за ≤ 120 c

### S-19 🏆 Лестница-часть 2: Stockfish UCI_Elo
- [ ] оппоненты SF UCI_Elo 1400/1600/1800 (threads=1); по инстансу на arq-процесс
- [ ] concurrency 2; семплирование ходов (10 %) в `bot_match_moves`
- **DoD:** матч против SF-1400; записи ходов для флага engine_likeliness

### S-20 📈 Elo и матчи UX
- [ ] Elo: старт 1000, K=32, clamp ±40 (ADR-008); `bot_matches`, `bot_stats`
- [ ] SSE-прогресс и реплей матча (пошагово); история Elo-график
- [ ] UI `/bots`: редактор (CodeMirror), тест-прогон, матч, лидерборд
- **DoD:** матч → итог → Elo обновлён → реплей смотрится

### S-21 🚩 trivial_bot
- [ ] детект: длина кода < порога; ходы «из кармана»; повторяющийся паттерн против random
- [ ] флаг в anticheat_flags с evidence
- **DoD:** тривиальный бот получает флаг, валидный не трогается

---

## E-08 · Античит 2.0 (S-22…S-24)

### S-22 🐞 Флаги-движок
- [ ] `anticheat_flags` (DDL → SPEC); правила-эвристики: confidence, evidence, статус-машина (new → reviewed)
- [ ] engine_likeliness по PGN: match rate SF-топ-1/3, точность; порог — config
- [ ] admin-руты review (teacher/admin)
- **DoD:** ставки флагов на реальных данных; false-positive ≈ 0 в тестовом наборе

### S-23 👨‍⚖️ LLM-judge (Decider)
- [ ] маршрут anticheat.judge_explain (Decider Flash V1.2), токены — бюджет школы
- [ ] сессии «объясни свой код/ход»: транскрипты; вердикт за учителем (ADR-005)
- **DoD:** judge-сессия запускается из UI, транскрипт виден учителю

### S-24 🧾 Плагиат и профиль-сверка
- [ ] plagiarism_suspected: сходство с эталонами/другими учениками (embeddings 768 + diff)
- [ ] profile_mismatch: кросс-доменная сверка (Advanced-шахматы при novice-циклах)
- [ ] кабинет учителя: лента флагов с приоритетом, карточка ученика
- **DoD:** все 5 типов флагов работают; кабинет учителя показывает ленту

---

## E-09 · PDF и полировка (S-25…S-26)

### S-25 📄 PDF-отчёт родителям
- [ ] порт report/pdf из annotator (fpdf2 + TTF, RU-шрифты)
- [ ] маршрут reports.parent_summary (L1): абзацы только из фактов
- [ ] UI: кнопка «PDF родителям» в карточке ученика; печать/фон задачи
- **DoD:** PDF по ученику генерируется за ≤ 10 с (фоном)

### S-26 🎨 Полировка UI и навигация
- [ ] dashboard `/`: сводка всех доменов; состояния загрузки/ошибок; тосты
- [ ] темы light/dark; мобильная вёрстка базовых экранов; чистовик RU-текстов
- **DoD:** демо-обход всей системы без застреваний

---

## E-10 · Стабилизация и релиз (S-27…S-29)

### S-27 🌐 e2e-набор
- [ ] Playwright: 7 сценариев (регистрация → email → задание → инсайт → бот-матч → дашборд → PDF)
- [ ] e2e-стенд на портах 8021/3201, изолированная БД `chessclass_e2e`
- **DoD:** e2e зелёные в CI при каждом PR

### S-28 📚 Документация и NFR
- [ ] `docs/SPEC.md` полный: DDL, API-схемы, таблицы промптов/весов/порогов
- [ ] `docs/RULES.md` полный; sprint-reports: ретроспектива этапа
- [ ] NFR-проверки (Design §2.3): p95 < 500 мс, матч ≤ 120 c, бюджеты
- **DoD:** NFR-чеклист пройден; SPEC/RULES — «жизнеспособные» единственные источники

### S-29 🚀 Релиз v0.1.0
- [ ] prod-compose (uvicorn workers=4 + nginx), миграции auto-run
- [ ] бэкапы nightly pg_dump (retention 14 д); restore-проверка
- [ ] тэг v0.1.0, changelog, финальный отчёт этапа
- **DoD:** демо на prod-стенде; релиз-отчёт

---

## Итоговая таблица

| Этап | Спринты | Время |
|---|---|---|
| E-01 Фундамент | S-01–S-03 | ~2 нед |
| E-02 LLM-шлюз | S-04–S-06 | ~1,5 нед |
| E-03 Python | S-07–S-09 | ~2 нед |
| E-04 Шахматы | S-10–S-12 | ~2 нед |
| E-05 RAG+ассистент | S-13–S-14 | ~1 нед |
| E-06 Навыки | S-15–S-16 | ~1 нед |
| E-07 Боты | S-17–S-21 | ~3 нед |
| E-08 Античит | S-22–S-24 | ~2 нед |
| E-09 PDF+UI | S-25–S-26 | ~1,5 нед |
| E-10 Релиз | S-27–S-29 | ~1,5 нед |
| **Итого** | **S-01–S-29** | **≈ 17–18 нед** |

**Демо-полки:** (S-03 · S-06 · S-09 · S-12 · S-14 · S-16 · S-21 · S-24 · S-26 · S-29).

<!-- §§NEXT§§ -->

