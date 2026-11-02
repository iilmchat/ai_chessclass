# Релиз v0.2.0 — ChessClass

**Дата:** 2026-11-02 · **Статус:** 16/16 спринтов (S-30…S-45), этапы E-11…E-16 ✅
**Предыдущий:** v0.1.0 (29/29, S-01…S-29)

## Что вошло

| Этап | Спринты | Результат |
|---|---|---|
| E-11 | S-30/S-31 | prod-стек, live RouterAI, FinOps/health |
| E-12 | S-32…S-37 | CodeMirror, SSE UI, доска, Playwright, e2e-стенд, очереди матчей |
| E-13 | S-38 | бэкапы/restore, edge TLS/HSTS, runbook |
| E-14 | S-39 | chess knowledge/RAG, insight/blunder, eval 13/13 |
| E-15 | S-40…S-42 | классы/учитель, auditor/аудит, прогресс/бейджи/age_group |
| E-16 | S-43…S-45 | этюды SF+LLM, озвучка, турниры/LMS-экспорт |

## Проверки

- Backend: **174 passed**, ruff/mypy 0.
- Frontend: **5 passed**, `tsc`/build 0.
- Playwright e2e: **7 passed** (полный journey).
- CI: S-30…S-45 зелёные (последний прогон — S-45).
- Миграции: head `0021_tournaments` (21).
- Prod: edge HTTPS/HSTS и backup/restore проверены в S-38.
- LLM: live RouterAI проверен в S-31 (4/4); в тестах — echo/без сети.

## Демо-аккаунты (dev)

- admin@chessclass.dev / dev-admin-2026
- teacher@chessclass.dev / dev-teacher-2026
- auditor@chessclass.dev / dev-auditor-2026
- student1@chessclass.dev, student2@chessclass.dev / dev-student-2026

## Ограничения / известные долги

- Voice: реальный ElevenLabs-ключ не предоставлен; без него — текстовый fallback.
- Этюды: курируемый пул кандидатов + SF; многоходовый solver не реализован.
- Турниры: синхронный запуск, без записи ходов/реплея и турнирного античита.
- Audit/voice/studies: retention/архивация не настроены (бэкапы БД есть).
- xAPI: statements готовы, LRS-коннектор — backlog.

## Следующий этап

v0.3 backlog (Design §2.2): PvP-матчи, Telegram, LMS-адаптеры, RS256/JWKS,
spaced repetition, расширение контента и наблюдаемости.
