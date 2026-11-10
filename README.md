# ChessClass — шахматно-программистский класс

Единая экосистема для школьников: Python-курс с безопасной песочницей, шахматная
лаборатория с разбором партий, конструктор ботов с лестницей Elo и когнитивный
дашборд навыков — **один профиль, один уровень, один LLM-ассистент** на все домены.

**Версия:** v0.7.1 (58/60 спринтов, релиз; S-81/S-84 отложены) · **Предыдущая:** v0.7.0
([release notes](docs/release-notes-v0.7.0.md)) · **© 2026 RuChating (iilmchat)**

[![CI](https://github.com/iilmchat/ai_chessclass/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/iilmchat/ai_chessclass/actions/workflows/ci.yml)
[![load](https://github.com/iilmchat/ai_chessclass/actions/workflows/load.yml/badge.svg?event=schedule)](https://github.com/iilmchat/ai_chessclass/actions/workflows/load.yml)
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fiilmchat-2496ED?logo=github)](https://github.com/iilmchat/ai_chessclass/pkgs/container/chessclass-backend)
— backend: lint (ruff) → typecheck (mypy) → alembic → seeds → pytest →
**pip-audit** → doc-lint; frontend: Vitest → tsc/build; e2e: Playwright
journey + **axe-core** → **backup→restore smoke**; ворота: **gitleaks**,
**docker build** api/web; **load** — еженедельный smoke с p95 в Step Summary
(PostgreSQL 17 + Redis сервисы; подробности — [docs/RULES.md](docs/RULES.md))

**Стек:** Python 3.12 + FastAPI · React 19 + TypeScript (Vite) · PostgreSQL 17 + pgvector ·
Redis 7 · Docker Compose · LLM-шлюз RouterAI (DeepSeek / MiniMax / Beam, локальный
фолбэк LM Studio) · Stockfish 17.1 · arq

---

## Возможности

- **Инфраструктура** — docker-compose dev-стек: PostgreSQL 17 (+pgvector) :5438,
  Redis :6384, FastAPI :8020, arq-воркер, Vite-фронтенд :3200; `/healthz` и
  `/readyz` (готовность + сверка ревизии миграций); 35 миграций Alembic.
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
- **RC v0.3.0 (S-56)** — e2e/smoke/backup, runbook `docs/runbooks/release-v0.3.0.md`.
- **Наблюдаемость/retention (S-46)** — метрики, cost-per-student, алерты,
  gzip-архив журналов/voice-кэша.
- **Auth-hardening (S-47)** — RS256/JWKS, аудит логинов/ролей, auditor scope,
  PII-анонимизация.
- **Prod** — edge TLS/HSTS, бэкапы/restore, runbook (S-38).
- **v0.4.0 (S-58…S-69)** — staging-контур (S-58), egress allowlist и CSP
  (S-61), hash-lock-сборка backend (S-62), CI-гейты + gitleaks + load-cron
  (S-63), gold-set eval и RAG-редактор (S-64), PvP-жалобы (S-65), a11y-гейт
  axe на 20 маршрутов и e2e 14 сценариев (S-66), LRS OAuth2 + LMS-mapping
  (S-67), Telegram webhook и teacher-события (S-68), релиз v0.4.0 (S-69).
- **v0.5.0 (S-70…S-74)** — circuit breaker/backoff LLM (S-70), OWASP LLM
  hardening и RAG-гейты (S-71), PostgreSQL RLS-изоляция классов (S-72),
  идемпотентность arq/DLQ/OpenTelemetry (S-73), parental consent +
  privacy/incident docs и релиз v0.5.0 (S-74).
- **v0.6 (S-75…)** — SMTP-доставка писем и enforcement родительского
  согласия для LLM/PDF (S-75), DLQ-операции/retry (S-76), OTel Collector +
  Grafana p95/error/trace_id (S-77), GPU-ключ/SSH-runbook (S-78), live LRS
  OAuth2, TTS fallback и a11y-доска (S-79); далее release v0.6.0.
- **v0.7 (S-81…S-85, релиз)** — prod-observability с Alertmanager и
  доставкой алертов в Telegram (S-82: OTel Collector → Tempo/Prometheus →
  Grafana, mTLS, retention 7/15 дней, профиль `observability`); внутренняя
  юридическая проверка privacy-policy/incident-response (РФ/ЕС/США) и
  consent enforcement v0.6.1: подтверждение возрастной группы ученика
  учителем, очередь `email_outbox` с retry/backoff для писем родителям
  (S-83); релиз v0.7.0 (S-85). Отложены: live staging-приёмка (S-81, ждёт
  боевых ключей LRS/TTS) и GPU-туннель (S-84, нет физической станции).
- **v0.7.1 (S-86…S-89, релиз)** — tech debt cleanup: `FOR UPDATE
  SKIP LOCKED` и retention `email_outbox` (S-86 ✅), observability hardening
  (S-87 ✅: маскировка логов, email-receiver, disk-alert), ротация
  сертификатов и retention ops (S-88 ✅: `check-cert-expiry.ps1`, gauges
  `email_outbox`/`retention archive`, runbook §7.1/§10.13), релиз v0.7.1
  (S-89 ✅). Юридический блокер снят: 16 вопросов `legal-review-v0.7.md`
  закрыты внешними договорённостями (решение юриста 2026-11-08).
- **v0.8 (S-90…S-94, в работе)** — Production Readiness: edge/auth hardening
  (S-90 ✅: реальный IP за прокси, per-account lockout, edge rate-limit 429,
  RS256/JWKS и `JWT_LEGACY_HS256=false`), object-level authorization
  (S-91 ✅: BOLA-хелперы, 403 на чужой объект, кросс-тенантные тесты),
  GHCR/Sentry/logrotate/multiprocess metrics (S-92 ✅), SMTP/offsite-бэкапы/
  песочница (S-93 ✅), релиз v0.8.0 (S-94).

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
| Версия | **v0.7.1** (2026-11-10, релиз) |
| Спринты | **58 закрыто** (S-30…S-89), этапы E-11…E-24 ✅; v0.7.1: S-86…S-89 ✅; S-81 ⏸️ (нет боевых ключей LRS/TTS), S-84 ⏸️ (нет физической станции) |
| Юридический блокер | ✅ снят: все 16 вопросов `docs/legal-review-v0.7.md` закрыты внешними договорённостями (решение юриста 2026-11-08) |
| Тесты backend | **328 passed** (число собранных тестов; факт — 325 passed + 3 skipped CSP-группы контейнеров; 203 база v0.3.0; +8 egress/S-61; +3 CSP-truth/S-61; +2 env-контракт/S-61; +3 hash-lock/S-62; +1 gold-set eval/S-64; +3 pvp-жалобы/S-65; +5 OAuth2/mapping/S-67; +8 telegram-webhook/события/S-68; +7 CB/backoff/S-70; +11 prompt-injection/S-71; +6 RLS-изоляция/S-72; +5 arq/DLQ/trace/S-73; +4 parental consent/S-74; +5 SMTP/enforcement/S-75; +1 DLQ operations/S-76; +3 OTel/HTTP metrics/S-77; +1 local API key/S-78; +2 LRS OAuth/TTS fallback/S-79; +6 email outbox/S-83; +4 teacher age confirmation/S-83; +10 observability config/S-82; +2 doc-lint прогресс/release-notes/S-85; +3 outbox SKIP LOCKED/index/retention/S-86; +3 observability hardening/S-87; +2 cert/retention ops/S-88; +4 edge/auth hardening/S-90; +7 object authz/S-91; +2 error tracking/S-92; +5 smtp/sandbox/backup S-93) |
| Тесты frontend | **5 passed** (Vitest: SSE-парсер/поток/reconnect) |
| UI-e2e | **16 passed** (Playwright: journey 7 + axe 2 + PvP 1 + RAG/review/ops/telegram/consent/chess-a11y 6) |
| Миграции | Alembic head **0035_s83_email_outbox** (35) |
| Ruff / MyPy / tsc | 0 / 0 / 0 |
| Seed-данные | 5 пользователей + 11 навыков + 5 skill_links + 16 заданий + 6 бейджей + 17 RAG-док |
| Следующий этап | v0.8.0 Production Readiness: S-90 edge/auth ✅, S-91 object authz ✅, S-92 CD/observability ✅, S-93 SMTP/backups/sandbox ✅, релиз v0.8.0 (S-94) ([TODO_V0.8.md](TODO_V0.8.md)) |

---

## Документация

Навигация: [docs/README.md](docs/README.md)

- [Design.md](Design.md) — архитектура и решения (источник истины, 20 разделов, ADR)
- [docs/SPEC.md](docs/SPEC.md) — контракты API v1 (эндпоинты, DTO, коды ошибок)
- [docs/RULES.md](docs/RULES.md) — процесс: спринты, git, docker-безопасность, отчёт
- [TODO_V0.2.md](TODO_V0.2.md) — завершённый план v0.2.0 (S-30…S-45)
- [TODO_V0.3.md](TODO_V0.3.md) — завершённый план v0.3.0 (S-46…S-57)
- [TODO_V0.4.md](TODO_V0.4.md) — завершённый план v0.4.0 (S-58…S-69)
- [TODO_V0.5.md](TODO_V0.5.md) — завершённый план v0.5.0 (S-70…S-74)
- [TODO_V0.6.md](TODO_V0.6.md) — завершённый план v0.6.0 (S-75…S-80)
- [TODO_V0.7.md](TODO_V0.7.md) — завершённый план v0.7.0 (S-81…S-85)
- [TODO_V0.7.1.md](TODO_V0.7.1.md) — завершённый план v0.7.1 (S-86…S-89)
- [TODO_V0.8.md](TODO_V0.8.md) — активный план v0.8.0 (S-90…S-94, Production Readiness)
- [docs/sprint-reports/S-86-2026-11-08.md](docs/sprint-reports/S-86-2026-11-08.md) — отчёт S-86
- [docs/sprint-reports/S-87-2026-11-08.md](docs/sprint-reports/S-87-2026-11-08.md) — отчёт S-87
- [docs/sprint-reports/S-88-2026-11-10.md](docs/sprint-reports/S-88-2026-11-10.md) — отчёт S-88
- [docs/sprint-reports/S-89-2026-11-10.md](docs/sprint-reports/S-89-2026-11-10.md) — отчёт S-89
- [docs/sprint-reports/S-90-2026-11-11.md](docs/sprint-reports/S-90-2026-11-11.md) — отчёт S-90
- [docs/sprint-reports/S-91-2026-11-11.md](docs/sprint-reports/S-91-2026-11-11.md) — отчёт S-91
- [docs/sprint-reports/S-92-2026-11-11.md](docs/sprint-reports/S-92-2026-11-11.md) - отчёт S-92
- [docs/sprint-reports/S-93-2026-11-11.md](docs/sprint-reports/S-93-2026-11-11.md) - отчёт S-93
- [deploy/logrotate/chessclass](deploy/logrotate/chessclass) — ротация файловых логов
- [docs/release-notes-v0.7.1.md](docs/release-notes-v0.7.1.md) — release notes v0.7.1
- [docs/release-notes-v0.7.0.md](docs/release-notes-v0.7.0.md) — release notes v0.7.0
- [docs/release-notes-v0.6.0.md](docs/release-notes-v0.6.0.md) — release notes v0.6.0
- [docs/release-notes-v0.5.0.md](docs/release-notes-v0.5.0.md) — release notes v0.5.0
- [docs/privacy-policy.md](docs/privacy-policy.md) — политика конфиденциальности
- [docs/incident-response.md](docs/incident-response.md) — план реагирования
- [docs/legal-review-v0.7.md](docs/legal-review-v0.7.md) — внутренний юр-ревью privacy/incident
- [TODO_V0.1.md](TODO_V0.1.md) — архив плана v0.1.0 (S-01…S-29)
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — изменения по спринтам
- [docs/runbooks/llm-gateway.md](docs/runbooks/llm-gateway.md) — LLM-шлюз: ключи, health, fallback
- [Ретроспектива v0.1.0](docs/sprint-reports/RETROSPECTIVE-E01-E10.md)
- Отчёты спринтов: [docs/sprint-reports/](docs/sprint-reports/)

---

## Лицензия

MIT License · © 2026 RuChating (iilmchat)
