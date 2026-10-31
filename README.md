# ChessClass — шахматно-программистский класс

Единая экосистема для школьников: Python-курс с безопасной песочницей, шахматная
лаборатория с разбором партий, конструктор ботов с лестницей Elo и когнитивный
дашборд навыков — **один профиль, один уровень, один LLM-ассистент** на все домены.

**Версия:** v0.1.0 (в разработке: S-01…S-03 из 29) · **© 2026 RuChating (iilmchat)**

[![CI](https://github.com/iilmchat/ai_chessclass/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/iilmchat/ai_chessclass/actions/workflows/ci.yml)
— lint (ruff) → typecheck (mypy) → alembic → seeds → pytest (PostgreSQL 17 + Redis
сервисы; подробности — [docs/RULES.md](docs/RULES.md))

**Стек:** Python 3.12 + FastAPI · React 19 + TypeScript (Vite) · PostgreSQL 17 + pgvector ·
Redis 7 · Docker Compose · LLM-шлюз RouterAI (DeepSeek / MiniMax / Beam, локальный
фолбэк LM Studio) — с этапа E-02 (S-04+)

---

## Возможности

**Готово (v0.1.0, этап E-01 «Фундамент»):**

- **Монорепозиторий и инфраструктура** — docker-compose dev-стек: PostgreSQL 17
  (+pgvector) :5438, Redis :6384, FastAPI :8020, arq-воркер, Vite-фронтенд :3200;
  `/healthz` (liveness DB+Redis) и `/readyz` (готовность + сверка ревизии миграций).
- **Аутентификация** — регистрация/логин, пароли **Argon2id**, access-JWT (15 мин)
  + refresh в HttpOnly-cookie (30 дней) с **ротацией** и защитой от reuse (отзыв
  всех сессий), email-верификация (dev — консольный SMTP), rate-limit и
  lockout 5 неудачных попыток/мин/IP, сброс пароля по одноразовому токену.
- **Профиль и уровни** — единый уровень `novice | intermediate | advanced`
  с маппингом доменных уровней (python basic/…/advanced, chess beginner/…/gm —
  ADR-002); уровень попадает в JWT; RBAC `student/teacher/admin`; teacher видит
  всех учеников платформы; пагинация `page`+`pageSize`.
- **Когнитивный реестр** — 11 навыков (python+chess) и 5 кросс-доменных связей
  `skill_links` (seeds, идемпотентные).
- **CI** — GitHub Actions: ruff, mypy, alembic, seeds, pytest на реальном
  PostgreSQL/Redis; локальный полный контур — `scripts/ci.ps1`.

**В разработке (этап v0.1.0):** LLM-шлюз RouterAI с маршрутами по уровням и
бюджетами в ₽ (S-04+), безопасная песочница Python (E-03), шахматный движок и
разбор партий (E-04), боты с лестницей Elo без LLM-расхода (E-05…E-07),
античит «только флаги», дашборд навыков и PDF родителям (E-08/E-09).
Дорожная карта — [TODO_V0.1.md](TODO_V0.1.md), архитектура — [Design.md](Design.md).

---

## Быстрый старт

```bash
git clone https://github.com/iilmchat/ai_chessclass.git
cd ai_chessclass
cp .env.example .env               # dev-значения уже рабочие; поменяйте секреты

docker compose -f docker-compose.dev.yml up -d --build   # db + redis + api + worker + web
docker compose -f docker-compose.dev.yml run --rm migrate # миграции alembic
docker compose -f docker-compose.dev.yml run --rm seed    # админ, ученики, навыки, связи
```

- Frontend: <http://localhost:3200> (дашборд с health-виджетом)
- API: <http://localhost:8020/healthz> · readiness: <http://localhost:8020/api/v1/readyz>
- Swagger: <http://localhost:8020/docs>

**Демо-аккаунты (только dev):** админ `admin@chessclass.dev` / `dev-admin-2026`,
ученики `student1@chessclass.dev` / `student2@chessclass.dev` — пароль
`dev-student-2026` (см. `.env.example`, `SEED_*`).

Тесты и проверки локально (полный контур в контейнере):

```powershell
.\scripts\ci.ps1            # migrate + seeds + ruff + mypy + pytest
```

> **Порты.** ADR-013: pg 5438, redis 6384 — изоляция от соседних проектов
> (KI-001: перед docker-действиями — `docker ps`, чужие контейнеры не трогаем).
> Полный env-контракт — Design §15.2 / `.env.example`.

---

## Статус

| Показатель | Значение |
|------------|----------|
| Версия | **v0.1.0.dev0** (2026-10-31, этап E-01 идёт) |
| Спринты | 1–3 из 29 (S-01 инфраструктура, S-02 auth, S-03 профиль/уровни/seeds) |
| Тесты backend | **19** (pytest, реальный PostgreSQL+Redis в контейнере) |
| Миграции | Alembic head **0003** (базис → auth → профиль/навыки) |
| Ruff / MyPy | 0 / 0 |
| TypeScript | strict-каркас (проверка типов — по мере наполнения фронтенда) |
| Seed-данные | 3 пользователя + 11 навыков + 5 skill_links |

---

## Документация

Навигация: [docs/README.md](docs/README.md)

- [Design.md](Design.md) — архитектура и решения (источник истины, 20 разделов, ADR-журнал)
- [docs/SPEC.md](docs/SPEC.md) — контракты API v1 (эндпоинты, DTO, коды ошибок)
- [docs/RULES.md](docs/RULES.md) — процесс: спринты, git, docker-безопасность, шаблон отчёта
- [TODO_V0.1.md](TODO_V0.1.md) — дорожная карта v0.1.0: 29 спринтов, этапы E-01…E-10
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — изменения по спринтам
- Отчёты спринтов: [S-01](docs/sprint-reports/S-01-2026-10-31.md) ·
  [S-02](docs/sprint-reports/S-02-2026-10-31.md) · [S-03](docs/sprint-reports/S-03-2026-10-31.md)

---

## Лицензия

MIT License · © 2026 RuChating (iilmchat)
