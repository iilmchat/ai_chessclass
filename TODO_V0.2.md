# TODO_V0.2.md — Спринты этапа v0.2.0 (ChessClass)

**Статус:** план · **Дата:** 2026-11-01 · **Производная от:** `Design.md` §2.2,
`docs/sprint-reports/RETROSPECTIVE-E01-E10.md`, `CHANGELOG.md`

> **Правила чтения.** v0.1.0 закрыт (29/29 спринтов, тег `v0.1.0`); здесь —
> следующий этап. Спринты продолжают нумерацию (S-30…S-45), этапы — E-11…E-16.
> Каждый спринт — вертикальный срез: миграция → код → API/UI → тесты → документы.
> Отчёт — `docs/sprint-reports/S-XX-YYYY-MM-DD.md` (шаблон — `docs/RULES.md` §7).
> Статусы: ☐ не начат · 🔶 в работе · ✅ готов · 🚫 блокер.

**Сводно:** 16 спринтов / 6 этапов. **Прогресс: 11/16 (S-30…S-40 ✅).** Сначала
закрываем технические хвосты v0.1.0 (E-11…E-13), затем — возможности v0.2
из Design §2.2 (E-14…E-16). Формула этапа: **сначала надёжность, потом
класс и вовлечение**.

---

## E-11 · Целостность релиза и живой LLM (S-30…S-31)

### S-30 ✅ Prod-стек и правда релиза
- [x] README / docs/README / docs/CHANGELOG / TODO_V0.1 — привести к факту
      v0.1.0 (29 спринтов, 148 тестов, 14 миграций, тег `316fce9`)
- [x] версии пакетов `0.1.0` (pyproject, `app.__version__`, frontend package.json,
      FastAPI `version`) — убрать `0.1.0.dev0`
- [x] `frontend/Dockerfile` (multi-stage node → nginx) + `frontend/nginx.conf`
      (SPA history fallback, proxy `/api/`, gzip, статика с cache)
- [x] prod-compose: `api --workers 4`, healthcheck, `migrate` до старта API,
      web из собственного образа, API опубликован только на loopback
- [x] `.env.prod.example`; `scripts/smoke-prod.ps1` (healthz/readyz/web)
- [x] worker: cron-путь `app.worker.scores_recalc` + регресс-тест
      (латентный рестарт-луп с S-16)
- **DoD:** `docker compose -f docker-compose.prod.yml config -q`; образ web
  собирается; prod-стек отвечает `readyz: ready`; README не врёт про версию ✅
  (2026-11-01: prod smoke OK + login через web-proxy; pytest 149, ruff/mypy 0;
  отчёт — `docs/sprint-reports/S-30-2026-11-01.md`)
- **Связь:** хвост S-29 (prod-compose без web-образа); nginx/TLS — S-38.

### S-31 ✅ Живой LLM-провайдер и FinOps
- [x] RouterAI: `LLM_BASE_URL` + `LLM_API_KEY` в env; слаги сверены с
      `GET /v1/models` (полные id), цены ₽/1M обновлены; judge —
      `google/gemini-3.1-flash-lite` (Decider — decisions-API, не chat)
- [x] `GET /admin/llm/health`: configured, модели, последний вызов, бюджеты,
      p95, расход за UTC-день; без ключа — `status: echo`
- [x] `scripts/llm_smoke.py`: 4 маршрута (L1/L2/L3/judge) + запись `llm_calls`
- [x] runbook: `docs/runbooks/llm-gateway.md` (ротация ключа, downgrade,
      локальный LM Studio, стоимость)
- **DoD:** 4 живых вызова `status=ok`, строки `llm_calls` id 88–91
  (2026-11-01); health live `status=ok`, все 5 тиров доступны; smoke без ключа
  возвращает код 2 (echo не маскируется). pytest 155, ruff/mypy 0.
- **Блокер:** снят 2026-11-01 — ключ RouterAI передан через `.env` (не в git).
- **Отчёт:** `docs/sprint-reports/S-31-2026-11-01.md`.

---

## E-12 · UX и e2e (S-32…S-35)

### S-32 ✅ CodeMirror в редакторах
- [x] зависимости `@codemirror/*`; общий `shared/CodeEditor.tsx` (Python,
      тема light/dark, отступы, скобки, поиск)
- [x] интеграция в PythonPage (решение) и BotsPage (код бота); ленивая загрузка
- [x] клавиатура/доступность, сохранение черновика, tsc/build
- **DoD:** оба редактора работают без потери состояния; bundle не растёт на
  первом экране (lazy chunk); tsc 0.
- **Факт:** `CodeEditor` — отдельный lazy-chunk 467.97 kB (gzip 157.16);
  main 355.57 kB (gzip 111.93, +1.81 kB к S-30). Черновики:
  `cc_draft:python:<id>` и `cc_draft:bots`. Браузер-проверка: оба редактора,
  номера строк, ввод, переключение задания, сохранение после reload.
- **Отчёт:** `docs/sprint-reports/S-32-2026-11-02.md`.

### S-33 ✅ SSE в UI
- [x] общий `useEventStream` (fetch/EventSource, токен, reconnect, last-event-id)
- [x] прогресс PGN-анализа и бот-матча на экране; fallback на polling
- [x] индикаторы «идёт/готово/ошибка», очистка подписки, тест хука
- **DoD:** прогресс виден без ручного refresh; обрыв связи восстанавливается;
  polling остаётся страховкой.
- **Факт:** `useEventStream` (fetch-SSE, Bearer, reconnect, Last-Event-ID);
  PGN: `status/progress/done` + blunders; матч: `running/done` (matchId
  создаётся до enqueue, SSE отдаёт позднему подписчику done); polling 2.5–3 с.
  Vitest: 5 тестов (парсер, поток, reconnect); `tsc`/build 0. Backend 156.
  CI: job `frontend` (npm ci/test/build).
- **Отчёт:** `docs/sprint-reports/S-33-2026-11-02.md`.

### S-34 ✅ Доска: drag-and-drop и мобильный UX
- [x] перетаскивание фигур, подсветка легальных ходов, отмена/повтор
- [x] ввод хода и FEN, адаптивная вёрстка, клавиатурный режим
- [x] тёмная тема доски, состояния загрузки/ошибки
- **DoD:** партия/позиция собирается мышью и с телефона; tsc 0; демо.
- **Факт:** `chess.js` (легальность, FEN, история), drag + click-to-move,
  подсветка целей/последнего хода/шаха, undo/redo, SAN/UCI-ввод, FEN-apply,
  переворот доски, light/dark square styles, responsive `.board-controls`.
  Браузер: drag e2→e4, click e2→e4, undo/redo, UCI `e7e5` + Enter, FEN apply,
  invalid FEN error, flip. `npm test` 5, build 404.37 kB (gzip 128.44).
- **Отчёт:** `docs/sprint-reports/S-34-2026-11-02.md`.

### S-35 ✅ Playwright UI-e2e
- [x] `@playwright/test`, конфиг, стенд 8021/3201, артефакты trace/video
- [x] 7 сценариев: регистрация → email → задание → инсайт → бот-матч →
      дашборд → PDF
- [x] CI-job, retries=1, отдельная БД (зависит от S-36)
- **DoD:** сценарии зелёные локально и в CI; падение даёт trace.
- **Факт:** `playwright.config.ts` (3201, trace/video retain-on-failure,
  retries=1); e2e/full-journey.spec.ts — 7/7 passed локально (56 с).
  Регистрация/verify/PDF — API+БД (dev-email), остальное — UI.
  CI job `e2e`: pg/redis services, API 8021, worker, Stockfish, fonts,
  Playwright; артефакты при падении. CI run 41357215595 — все job'ы ✅.
- **Отчёт:** `docs/sprint-reports/S-35-2026-11-02.md`.

---

## E-13 · Эксплуатация и масштаб (S-36…S-38)

### S-36 ✅ Отдельная e2e-БД и стенд
- [x] compose-profile `e2e`: `chessclass_e2e`, порты 8021/3201, seed
- [x] изоляция от dev-БД; очистка между прогонами; CI-сервис
- **DoD:** e2e не трогает dev-данные; параллельный запуск с dev-стеком.
- **Факт:** `docker-compose.e2e.yml` (project `chessclass_e2e`, db 5439,
  redis 6385, api 8021, web 3201, volumes `chessclass_e2e_*`); setup-сервис
  делает migrate+seed. `scripts/e2e.ps1 test` — reset → up → Playwright →
  down -v. Прогон при работающем dev-стеке: **7 passed (15.9 с)**, dev-БД
  не тронута. CI job `e2e` использует отдельные pg/redis services.
- **Отчёт:** `docs/sprint-reports/S-36-2026-11-02.md`.

### S-37 ✅ Concurrency матчей и справедливость
- [x] per-queue лимиты (SF/random/greedy/minimax), максимум 5 матчей
- [x] round-robin по id очередей вместо FIFO (Design §11.1)
- [x] нагрузочный тест, метрики длительности/отказов, таймауты
- **DoD:** 5 матчей параллельно укладываются в бюджет; нет голодания очередей.
- **Факт:** per-queue воркеры `arq:matches:{random,greedy,minimax,sf}`
  (2/1/1/1), API 429 `match_limit` при >5 активных; `GET
  /admin/matches/metrics` (p95, timeouts, refused, queue lengths/active);
  `scripts/match_load.py` — 5/5 finished за 21.5 с (random×2, greedy,
  minimax2, SF-1400), все очереди отработали; unit-тест 6-го матча 429.
  Backend 159 passed; e2e 7 passed (27.6 с).
- **Отчёт:** `docs/sprint-reports/S-37-2026-11-02.md`.

### S-38 ✅ Бэкапы, TLS и runbook
- [x] nightly `pg_dump` (cron/контейнер, retention 14 дней), sha256
- [x] restore-скрипт + учебное восстановление на копии
- [x] nginx edge: TLS (сертификаты/Let's Encrypt), security headers, HSTS
- [x] runbook: деплой, откат, ротация секретов, инциденты
- **DoD:** бэкап создаётся по расписанию; restore проверен; HTTPS-вход.
- **Факт:** `backup.sh`/`backup.ps1` (sha256, lock, retention 14),
  `restore-test.ps1` (temp DB, users/alembic), `install-backup-task.ps1`
  + cron; edge nginx 80→443, TLS/HSTS/security headers, self-signed + LE
  runbook; smoke prod HTTPS OK, restore prod-дампа users=3 alembic=0014.
- **Отчёт:** `docs/sprint-reports/S-38-2026-11-02.md`; runbook —
  `docs/runbooks/operations.md`.

---

## E-14 · Шахматные знания (S-39)

### S-39 ✅ INSIGHT knowledge для шахмат
- [x] ingest дебютов/фаз/метаданных партий в `rag_*` (домен `chess`)
- [x] retrieval по FEN/дебюту/фазе; knowledge-блок в `chess_lab.insight`
      и `chess_lab.blunder` (факты SF не правятся)
- [x] eval-набор (10 позиций), метрики релевантности, админ-просмотр
- **DoD:** инсайт ссылается на релевантный фрагмент; факты SF неизменны;
  eval ≥ baseline.
- **Факт:** 10 новых chess-документов (13 всего), `rag/chess.py`
  (фаза/запрос/lexical rerank), knowledge в insight/blunder + UI;
  `chess_rag_eval.py` — 13/13 (10 текстовых + 3 FEN); backend 162.
- **Отчёт:** `docs/sprint-reports/S-39-2026-11-02.md`.

---

## E-15 · Класс и учитель (S-40…S-42)

### S-40 ✅ Группы и классы
- [x] `classes`, `class_members` (DDL → SPEC); инвайты, роли teacher/student
- [x] API классов, групповой дашборд (навыки/флаги/матчи), RBAC
- [x] UI кабинета учителя: список классов, карточка класса
- **DoD:** учитель создаёт класс, добавляет ученика, видит срез; чужой класс — 403.
- **Факт:** миграция `0015_classes`; `domains/classes` (service/router),
  8 endpoints; invite-код/ротация, join, add/remove; dashboard
  (11 навыков + флаги + матчи/Elo); seed teacher; UI `/classes`;
  backend 164, frontend 5, build OK.
- **Отчёт:** `docs/sprint-reports/S-40-2026-11-02.md`.

### S-41 ☐ Роль auditor и журнал аудита
- [ ] роль `auditor` (read-only) + миграция; доступ к флагам/вердиктам/PDF
- [ ] `audit_log` (кто/что/когда/источник), запись чувствительных действий
- [ ] экспорт журнала (CSV) и фильтры
- **DoD:** auditor видит, но не меняет; действия учителя попадают в журнал.

### S-42 ☐ Достижения, стрики и age_group
- [ ] `py_progress` (решено/темы/стрики), `achievements` (бейджи)
- [ ] события достижений, недельные стрики, UI профиля
- [ ] `age_group` в профиле (Design §4.3), безопасные дефолты
- **DoD:** стрик растёт/сбрасывается по правилам; бейдж выдаётся один раз.

---

## E-16 · Контент и вовлечение (S-43…S-45)

### S-43 ☐ Генерация этюдов «код + LLM»
- [ ] генератор позиций SF + LLM-оформление условия (маршрут `chess_lab.*`)
- [ ] авто-тесты/эталон, очередь ревью учителя, публикация
- [ ] античит-проверки сгенерированного контента, лимиты бюджета
- **DoD:** 5 этюдов проходят ревью и решаются; брак отклоняется.

### S-44 ☐ Озвучка ответов (ElevenLabs)
- [ ] провайдер voice (ElevenLabs), кэш аудио, квоты и стоимость
- [ ] маршрут `voice.speak`, UI-плеер в инсайте/комментарии
- [ ] graceful fallback на текст без ключа
- **DoD:** ответ озвучивается, кэш повторно не платит; без ключа — текст.

### S-45 ☐ Турниры ботов и экспорт в LMS
- [ ] турнир: сетка/round-robin, расписание, лидерборд, античит-флаги
- [ ] экспорт результатов/навыков (CSV, xAPI-совместимый payload)
- [ ] UI турниров и страница экспорта; документация
- **DoD:** турнир из 8 ботов играется без LLM; экспорт валиден.

---

## Зависимости и порядок

1. **S-30** — фундамент эксплуатации; без него не считаем v0.2 начатым.
2. **S-31** — параллельно S-30, требует ключ RouterAI.
3. **S-32/S-33/S-34/S-35** — после S-30; S-35 CI использует services,
   S-36 — отдельный e2e-стенд.
4. **S-36…S-38** — после S-30; S-38 последним в E-13.
5. **S-39** — после S-31 (живые embeddings/LLM).
6. **E-15** — после E-12/E-13 (стабильный UI и стенд).
7. **E-16** — после E-15; S-44 дополнительно требует S-31.

## Демо-полки

S-30 (prod-стек) · S-33 (SSE) · S-35 (Playwright) · S-38 (бэкап/TLS) ·
S-42 (класс/достижения) · S-45 (турниры/экспорт).

## Не входит в v0.2 (backlog Design §2.2)

Telegram-бот, spaced-repetition, разбор чужих партий, интеграции со школами,
PvP-матчи ботов в реальном времени, мобильные приложения, RS256/JWKS,
мультитенантность. Возвращаться после v0.2.0 по метрикам использования.

## Критерий релиза v0.2.0

- 16/16 спринтов ✅, отчёты и CHANGELOG актуальны
- тесты: backend + Playwright зелёные; ruff/mypy/tsc 0
- миграции head соответствует SPEC; prod-стек с HTTPS и бэкапами
- живой LLM хотя бы на одном маршруте каждого домена (или явный echo-режим)
- демо-обход: ученик → учитель → родитель → админ
