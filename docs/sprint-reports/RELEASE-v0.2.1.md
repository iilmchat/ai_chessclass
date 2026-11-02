# Релиз v0.2.1 — патч prod-приёмки

**Дата:** 2026-11-02 · **База:** v0.2.0 (16/16 спринтов)

## Исправлено

- `docker-compose.prod.yml`: `LLM_EMBED_MODEL` по умолчанию пустой
  (`${LLM_EMBED_MODEL:-}`), а не несуществующий у RouterAI
  `nomic-embed-text-v1.5`. Пустое значение включает hash-эмбеддинги без
  сетевых вызовов и HTTP 400 при seed.
- Версии пакетов/API/frontend подняты до `0.2.1`.

## Приёмка v0.2.0 (кратко)

- Миграции head `0021_tournaments`, seed 5 пользователей + 6 бейджей.
- HTTPS-edge/HSTS, `/healthz`, `/readyz` — OK.
- Live RouterAI: 4/4 маршрута `status=ok`.
- Классы/аудит, генерация этюда → ревью → решение, турнир 8 ботов
  (7 матчей), LMS CSV/xAPI — OK.
- Backup/restore: `users=5`, `alembic=0021_tournaments`.

Полный отчёт — `docs/sprint-reports/ACCEPTANCE-v0.2.0-prod-2026-11-02.md`.
