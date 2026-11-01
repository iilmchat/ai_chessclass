# Прогресс сессии 2026-11-01 (автономный режим) — обновление 2

Спринты S-11…S-21 (11 спринтов за сессию) — все ✅, закоммичены и запушены
в https://github.com/iilmchat/ai_chessclass (main).

## Готово по этапам

- **E-01 Фундамент** ✅ (S-01…S-03)
- **E-02 LLM-шлюз** ✅ (S-04…S-06)
- **E-03 Python-домен** ✅ (S-07…S-09)
- **E-04 Шахматный домен** ✅ (S-10…S-12)
- **E-05 RAG и сквозной ассистент** ✅ (S-13…S-14)
- **E-06 События навыков** ✅ (S-15…S-16)
- **E-07 Лаборатория ботов** ✅ (S-17…S-21)

## Состояние

- Тесты: **139 passed** · ruff 0 · mypy 0 (133 файла) · tsc 0
- Миграции: head `0012_bot_matches` (12 миграций)
- API v1: healthz/readyz, auth (8), profile (5), py (8), chess (8+),
  skills (4), bots (7+replay/SSE/leaderboard), admin (models/finops/rag)
- 17 отчётов спринтов + CHANGELOG + SPEC (10 разделов) + README/LICENSE
- Стек живой: api/worker(SF 17.1, APP_ROLE=worker)/web/db/redis

## Осталось до v0.1.0 (8 спринтов)

1. **S-22…S-24 — E-08 Античит 2.0**: флаги-движок (engine_likeliness по
   sf_sample-семплам против топ-1 SF), дашборд учителя флагов
   (GET /admin/anticheat/flags + review), unexplained_code (judge-сессия).
2. **S-25…S-26 — E-09 Отчёты**: PDF родителям (fpdf2 + TTF, reports_*),
   дашборд учителя (класс × навыки).
3. **S-27…S-29 — E-10 Полировка**: prod-compose, nginx, бэкапы,
   security-заголовки, e2e Playwright, релиз v0.1.0.

## Известные хвосты (не блокеры)

- Матчи: concurrency 2 (§7.2) — ограничение per-очередь при росте;
  SSE-прогресс в UI — polling пока; Elo-график — с историей матчей.
- Инсайт без knowledge для шахмат (запрос от метаданных партий/ECO).
- dev-target Dockerfile (dev-депы в run-контейнере ~40 с на прогон).
