# Релиз v0.1.0 — ChessClass «Шахматно-программистский класс»

**Дата:** 2026-11-01 · 29/29 спринтов · этапы E-01…E-10 завершены

## Экосистема

Единая система для школьников: Python-курс с безопасной песочницей,
шахматная лаборатория с разбором партий, конструктор ботов с лестницей Elo
(до Stockfish UCI_Elo 1800), когнитивный дашборд из 11 навыков с
рекомендациями, античит «только флаги» и PDF-отчёты родителям.

## Ключевые возможности v0.1.0

- **Единый профиль и уровень** novice/intermediate/advanced (ADR-002)
  с маппингом доменных уровней; JWT + HttpOnly-refresh с ротацией
- **LLM-шлюз RouterAI**: 10 маршрутов × уровни, L1/L2/L3/judge, квоты и
  бюджеты (free 50k / pro 500k), fallback cloud → LM Studio → echo,
  FinOps (llm_calls/usage_daily, ₽/1M)
- **Песочница RestrictedPython 8.5**: AST-отсечки, белый список импортов,
  RLIMIT 256 МБ, per-run 5 с, обрезка вывода 64 КБ
- **Python-домен**: 16 заданий с assert-тестами, лестница подсказок
  (seeded → LLM), LLM-комментарии, low_effort/plagiarism-детект
- **Шахматы**: Stockfish 17.1, инсайт позиции (факты SF + LLM-объяснение),
  PGN-анализ с блюндер-детектом (Δeval ≥ 300 cp), SSE-прогресс
- **Боты**: SafePosition-контракт, лестница random/greedy/minimax2/SF-Elo,
  матчи на arq (без LLM), Elo K=32 clamp ±40, лидерборд, реплей
- **Античит 2.0**: только флаги (engine_likeliness, low_effort, trivial_bot,
  plagiarism_suspected, profile_mismatch, unexplained_code) — решает учитель
- **Когнитивный дашборд**: 11 навыков, недельные EMA (α=0.3), spider-график,
  рекомендации по skill_links
- **PDF родителям**: fpdf2 + DejaVuSans (кириллица)

## Команда

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml run --rm migrate
docker compose -f docker-compose.dev.yml run --rm seed
```

Frontend: http://localhost:3200 · API: http://localhost:8020/docs

## Метрики

148 тестов (юнит + интеграционные + e2e-journey) · ruff/mypy/tsc — 0
ошибок · 14 миграций Alembic · 29 отчётов спринтов

## Известные ограничения (→ v0.2)

- LLM-провайдер в echo-режиме без ключа (контракты проверены)
- Playwright UI-сценарии, CodeMirror, drag-drop доски — полировка
- prod-compose без nginx/TLS (каркас в docker-compose.prod.yml)
