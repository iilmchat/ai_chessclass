# RULES.md — Процесс ChessClass

> **Назначение.** Правила работы: спринты, отчёты, git, docker-безопасность,
> валидация перед коммитом. План — `TODO_V0.1.md`; решения — `Design.md`.

## 1. Источники истины

| Что | Где | Примечание |
|---|---|---|
| Архитектура, ADR | `Design.md` | при расхождении побеждает Design |
| Контракты API/DTO | `docs/SPEC.md` | живой реестр |
| План и DoD спринтов | `TODO_V0.2.md` (активный), `TODO_V0.1.md` (архив) | статусы ☐/🔶/✅ |
| Процесс | `docs/RULES.md` | этот файл |

Правило **«один факт — один источник»**: факт живёт в одном месте, остальные
документы ссылаются. Новый факт → сначала Design/приёмка, затем код, потом ссылки.

## 2. Языки

- Документация, комментарии, отчёты — **русский**.
- Идентификаторы кода (переменные, функции, ветки, коммиты) — **латиница**.
- Самодисциплина: не смешивать алфавиты внутри одного слова (латинская буква «e»
  и кириллическая «е» выглядят одинаково); grep-аудит перед коммитом ловит
  смешанные слова, находки фиксируются в отчёте спринта.

## 3. Спринты

1. Старт: в активном `TODO_V0.2.md` статус спринта 🔶; сверка чек-листа с реальностью.
2. Работа вертикальными срезами: код ↔ тесты ↔ миграция ↔ документация.
3. Финиш: сверить DoD спринта, перевести статус в ✅, написать отчёт
   `docs/sprint-reports/S-XX-YYYY-MM-DD.md` (шаблон — §7), коммит.
4. Спринт не закрывается при незакрытом 5xx или сломанном docker-стеке.

## 4. Git

- Ствол `main`; работаем в ветках `feat/s-xx-<суть>`, `fix/...`, `docs/...`.
- Коммиты: conventional (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`).
- Первый коммит репозитория — `chore: bootstrap S-01 monorepo skeleton`.
- Спринт ≈ 1–3 ветки; при вливании — squash.

## 5. Docker-безопасность (KI-001)

1. **Перед любым docker-действием** — `docker ps`: соседние проекты
   (`ai_teacher_*`, `ai-chess-annotator-*`) держат порты 5436/5437/6383/6385 —
   их не трогаем.
2. Наш проект: контейнеры `chessclass-*`, сеть `chessclass-net`, volumes
   `chessclass_pgdata` / `chessclass_redisdata`.
3. Порты (ADR-013): pg **5438**, redis **6384**, api **8020**, web **3200**,
   e2e **8021/3201**. Изменение порта — только через новый ADR.
4. Никаких `docker system prune -a` / `docker network prune` без явного
   подтверждения пользователя.
5. Единственный канал запуска стека: `docker compose -f docker-compose.dev.yml ...`.

## 6. Валидация перед коммитом

| Что | Как |
|---|---|
| Compose | `docker compose -f docker-compose.dev.yml config -q` |
| Backend статика | `ruff check . && mypy .` (в `backend/`) |
| Backend тесты | `scripts/ci.ps1` — полный контур в контейнере (host-pip нестабилен); альтернатива: venv `backend/.venv` |
| Frontend типы | `npx tsc --noEmit` (в `frontend/`) |
| healthz | `curl http://localhost:8020/healthz` → `{"status":"ok","db":true,"redis":true}` |
| readyz | `curl http://localhost:8020/readyz` → `status: ready`, `migrationsUpToDate: true` |
| Фронтенд | `http://localhost:3200` — на дашборде «API/БД/Redis — ок» |
| CI (GitHub) | `.github/workflows/ci.yml`: backend ruff → mypy → alembic → seeds → pytest (pg+redis); frontend npm test → npm run build (Node 22) |

## 7. Шаблон отчёта спринта

Файл: `docs/sprint-reports/S-XX-YYYY-MM-DD.md`.

```markdown
# Отчёт S-XX — <название>

## 1. Что сделано
- …

## 2. DoD
- [ ] <критерий из активного TODO (v0.2 — TODO_V0.2.md)> — ✅/❌
      (доказательство: команда/лог/ссылка)

## 3. Что не сделано / блокеры

## 4. Отклонения от Design (нужен ADR?)

## 5. Новые факты → Design (обязаны вернуться в Design?)

## 6. Риски

## 7. Следующий спринт — S-XX+1: <название>
```
