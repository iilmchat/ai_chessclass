# Нагрузочный профиль (S-55)

**Дата:** 2026-11-03 · dev-стек, API `http://localhost:8020`.

## 1. Что измерялось

Скрипт `backend/scripts/load_smoke.py` — health/ready под конкурентной
нагрузкой; LLM/Stockfish/матчи не нагружались (они async и внешние).

```powershell
docker compose -f docker-compose.dev.yml exec -T api \
  python scripts/load_smoke.py --base-url http://localhost:8020 \
  --requests 30 --concurrency 5 --p95-ms 300
```

## 2. Результат dev (2026-11-03)

| Профиль | Запросы | Concurrency | p50 | p95 | Ошибки | Цель p95 |
|---|---:|---:|---:|---:|---:|---:|
| `/healthz` | 30 | 5 | 43.2 мс | **76.0 мс** | 0 | 300 мс dev |

`/readyz` отдельно ~500–620 мс (проверки DB/Redis); для k8s readiness
это приемлемо, но в общий p95 health не включается.

## 3. Целевые p95 (prod-ориентир)

| Класс | p95 |
|---|---:|
| health/ready (ready допускается 800 мс) | 150 / 800 мс |
| auth/login (Argon2) | 500 мс |
| read API (skills/tournaments/review) | 300 мс |
| LLM/voice | вне SLA, async/таймауты |
| матчи/турниры | async arq, статус через SSE |

## 4. Ограничения

- Нагрузка на матчи/турниры требует worker+Stockfish и не входит в smoke;
  для неё — отдельный профиль на staging (S-56).
- LLM-провайдер внешний; p95 зависит от RouterAI/LM Studio.
- Dev API — один uvicorn-worker; prod масштабируется репликами.
- `readyz` делает реальные ping DB/Redis; при недоступности — 503.

## 5. Как повторить

1. Поднять dev-стек (`docker compose -f docker-compose.dev.yml up -d`).
2. Запустить скрипт (см. выше), при необходимости `--include-ready`.
3. Для staging/RC — base-url prod, `--requests 100 --concurrency 20`,
   p95-ms по таблице; результат приложить к S-56.
