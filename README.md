# ChessClass — шахматно-программистский класс

Единая экосистема для школьников: Python-курс с безопасной песочницей, шахматная
лаборатория с разбором партий, конструктор ботов с лестницей Elo и когнитивный
дашборд навыков — **один профиль, один уровень, один LLM-ассистент** на все домены.

**Версия:** v0.2.1 (16/16 спринтов, патч после prod-приёмки) · **Предыдущая:** v0.2.0
([TODO_V0.2.md](TODO_V0.2.md)) · **© 2026 RuChating (iilmchat)**

[![CI](https://github.com/iilmchat/ai_chessclass/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/iilmchat/ai_chessclass/actions/workflows/ci.yml)
— backend: lint (ruff) → typecheck (mypy) → alembic → seeds → pytest; frontend:
Vitest → tsc/build; e2e: Playwright journey (PostgreSQL 17 + Redis сервисы;
подробности — [docs/RULES.md](docs/RULES.md))

**Стек:** Python 3.12 + FastAPI · React 19 + TypeScript (Vite) · PostgreSQL 17 + pgvector ·
Redis 7 · Docker Compose · LLM-шлюз RouterAI (DeepSeek / MiniMax / Beam, локальный
фолбэк LM Studio) · Stockfish 17.1 · arq

---

## Возможности v0.2.0

- **Инфраструктура** — docker-compose dev-стек: PostgreSQL 17 (+pgvector) :5438,
  Redis :6384, FastAPI :8020, arq-воркер, Vite-фронтенд :3200; `/healthz` и
  `/readyz` (готовность + сверка ревизии миграций); 21 миграция Alembic.
- **Аутентификация** — регистрация/логин, Argon2id, access-JWT (15 мин) +
  refresh в HttpOnly-cookie (30 дней) с ротацией и защитой от reuse, email-
  верификация, rate-limit/lockout, сброс пароля.
- **Профиль и уровни** — единый уровень `novice | intermediate | advanced`
  с маппингом доменных уровней (ADR-002), JWT-клейм, RBAC `student/teacher/admin`,
  пагинация; 11 навыков и 5 кросс-доменных связей.
- **LLM-шлюз RouterAI** — 11 маршрутов × уровни L1/L2/L3/judge, квоты и бюджеты
  (free 50k / pro 500k токенов/день), fallback cloud → LM Studio → echo,
  FinOps (`llm_calls`, `usage_daily`, цены ₽/1M).
- **Python-домен** — 16 заданий с assert-тестами, RestrictedPython-песочница
  (AST-отсечки, белый список импортов, 256 МБ, timeout, обрезка вывода),
  лестница подсказок, LLM-комментарии, low_effort/plagiarism-детект.
- **Шахматы** — Stockfish 17.1, инсайт позиции (факты SF + LLM-объяснение),
  PGN-анализ с блюндер-детектом (Δeval ≥ 300 cp), SSE-прогресс.
- **Боты** — SafePosition-контракт, лестница random/greedy/minimax2/SF-Elo
  1400–1800, матчи на arq без LLM-расхода, Elo K=32 clamp ±40, лидерборд, реплей.
- **Античит 2.0** — только флаги: engine_likeliness, low_effort, trivial_bot,
  plagiarism_suspected, profile_mismatch, unexplained_code; решение за учителем.
- **Когнитивный дашборд** — 11 навыков, недельные EMA (α=0.3), spider-график,
  рекомендации по skill_links.
- **PDF родителям** — fpdf2 + DejaVuSans (кириллица), фоновая генерация.
- **Классы и учитель (S-40)** — `classes`/`class_members`, инвайт-коды,
  групповой дашборд (навыки/флаги/матчи), RBAC owner-teacher.
- **Аудит и auditor (S-41)** — роль read-only, `audit_logs`, фильтры и CSV,
  запись действий классов/античита/PDF.
- **Прогресс и бейджи (S-42)** — `py_progress`, стрики, 6 достижений,
  `age_group`, UI профиля.
- **Этюды SF + LLM (S-43)** — генерация, ревью teacher, публикация,
  попытки решения; лимит генераций.
- **Озвучка ElevenLabs (S-44)** — TTS с кэшем/квотой и текстовым fallback.
- **Турниры и LMS (S-45)** — bracket/round-robin без LLM, CSV/xAPI-экспорт.
- **Турниры v2 (S-48)** — async arq/SSE, replay, отмена, recovery, SF-античит.
- **LMS LRS (S-49)** — xAPI-очередь, retry/идемпотентность, журнал доставки.
- **Telegram (S-50)** — consent/код привязки, outbox уведомлений, отписка.
- **PvP (S-51)** — комнаты/quick-match, SSE/replay, отдельный PvP-Elo.
- **Повторение (S-52)** — SM-2 карточки ошибок Python/шахмат, дневной лимит.
- **Этюды v2 (S-53)** — random-playout, дедуп FEN, PV-solver, авто-ревью.
- **RAG-редактор (S-54)** — версии/лицензии, hybrid FTS+vector, PDF/MD.
- **Качество (S-55)** — load smoke p95, a11y skip-link/focus, security headers.
- **Наблюдаемость/retention (S-46)** — метрики, cost-per-student, алерты,
  gzip-архив журналов/voice-кэша.
- **Auth-hardening (S-47)** — RS256/JWKS, аудит логинов/ролей, auditor scope,
  PII-анонимизация.
- **Prod** — edge TLS/HSTS, бэкапы/restore, runbook (S-38).

---

## Быстрый старт (dev)

```bash
git clone https://github.com/iilmchat/ai_chessclass.git
cd ai_chessclass
cp .env.example .env               # dev-значения рабочие; поменяйте секреты

docker compose -f docker-compose.dev.yml up -d --build   # db + redis + api + worker + web
docker compose -f docker-compose.dev.yml run --rm migrate # миграции alembic
docker compose -f docker-compose.dev.yml run --rm seed    # админ, ученики, навыки, связи
```

- Frontend: <http://localhost:3200>
- API: <http://localhost:8020/healthz> · readiness:
  <http://localhost:8020/api/v1/readyz> · Swagger: <http://localhost:8020/docs>

**Демо-аккаунты (только dev):** админ `admin@chessclass.dev` / `dev-admin-2026`,
учитель `teacher@chessclass.dev` / `dev-teacher-2026`, аудитор
`auditor@chessclass.dev` / `dev-auditor-2026`, ученики
`student1@chessclass.dev` / `student2@chessclass.dev` — пароль
`dev-student-2026` (см. `.env.example`, `SEED_*`).

Тесты и проверки локально (полный контур в контейнере):

```powershell
.\scripts\ci.ps1            # migrate + seeds + ruff + mypy + pytest

cd frontend
npm test                    # Vitest: SSE-парсер/поток/reconnect
npm run test:e2e            # Playwright против dev api+worker
```

Изолированный e2e-стенд (8021/3201, своя БД, очистка):

```powershell
.\scripts\e2e.ps1 test      # reset -> up -> Playwright -> down -v
```

**Prod:** `docker-compose.prod.yml` (web-образ, healthchecks, миграции,
edge-TLS, бэкапы) — S-30/S-38 ✅; детали — [TODO_V0.2.md](TODO_V0.2.md).

> **Порты.** ADR-013: pg 5438, redis 6384 — изоляция от соседних проектов
> (KI-001: перед docker-действиями — `docker ps`, чужие контейнеры не трогаем).
> Полный env-контракт — Design §15.2 / `.env.example`.

---

## Статус

| Показатель | Значение |
|------------|----------|
| Версия | **v0.2.1** (2026-11-02, патч prod-приёмки) |
| Спринты | **16/16** (S-30…S-45), этапы E-11…E-16 ✅ |
| Тесты backend | **174 passed** (юнит + интеграционные + e2e-journey) |
| Тесты frontend | **5 passed** (Vitest: SSE-парсер/поток/reconnect) |
| UI-e2e | **7 passed** (Playwright: полный journey) |
| Миграции | Alembic head **0021_tournaments** (21) |
| Ruff / MyPy / tsc | 0 / 0 / 0 |
| Seed-данные | 5 пользователей + 11 навыков + 5 skill_links + 16 заданий + 6 бейджей + 13 RAG-док |
| Следующий этап | **v0.3** — backlog Design §2.2 (PvP, Telegram, LMS-адаптеры), план — [TODO_V0.3.md](TODO_V0.3.md) |

---

## Документация

Навигация: [docs/README.md](docs/README.md)

- [Design.md](Design.md) — архитектура и решения (источник истины, 20 разделов, ADR)
- [docs/SPEC.md](docs/SPEC.md) — контракты API v1 (эндпоинты, DTO, коды ошибок)
- [docs/RULES.md](docs/RULES.md) — процесс: спринты, git, docker-безопасность, отчёт
- [TODO_V0.2.md](TODO_V0.2.md) — завершённый план v0.2.0 (S-30…S-45)
- [TODO_V0.3.md](TODO_V0.3.md) — план v0.3.0 (S-46…S-57)
- [TODO_V0.1.md](TODO_V0.1.md) — архив плана v0.1.0 (S-01…S-29)
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — изменения по спринтам
- [docs/runbooks/llm-gateway.md](docs/runbooks/llm-gateway.md) — LLM-шлюз: ключи, health, fallback
- [Ретроспектива v0.1.0](docs/sprint-reports/RETROSPECTIVE-E01-E10.md)
- Отчёты спринтов: [docs/sprint-reports/](docs/sprint-reports/)

---

## Лицензия

MIT License · © 2026 RuChating (iilmchat)
