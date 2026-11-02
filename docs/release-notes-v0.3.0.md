# ChessClass v0.3.0 — release notes

**Дата:** 2026-11-03 · **Тип:** minor (v0.3.0) · **Предыдущая:** v0.2.1

## Главное

- **S-46 Наблюдаемость/retention:** `/metrics`, alerts/costs/CSV, UI `/ops`,
  gzip-архив и retention.
- **S-47 Auth-hardening:** RS256/JWKS, legacy HS256, auth audit, auditor
  scope, role/anonymize API, PII.
- **S-48 Турниры v2:** async arq/SSE, replay, cancel/recovery, SF-античит.
- **S-49 LMS LRS:** xAPI-очередь, идемпотентность, retry, журнал доставки.
- **S-50 Telegram:** consent/код/deep-link, outbox, отписка, graceful off.
- **S-51 PvP:** комнаты/quick-match, SSE/replay, отдельный PvP-Elo, жалобы.
- **S-52 Повторение:** SM-2 карточки ошибок Python/шахмат, UI `/review`.
- **S-53 Этюды v2:** random-playout, дедуп FEN, PV-solver, авто-ревью.
- **S-54 RAG-редактор:** версии/лицензии, publish/rollback, hybrid FTS+vector,
  импорт MD/PDF, eval.
- **S-55 Качество:** load smoke p95, a11y skip-link/focus, security headers,
  pip-audit/secrets scan.
- **S-56/57 RC/релиз:** миграции head `0028_rag_editor`, backup/restore,
  e2e 7/7, smoke, тег и GitHub Release.

## Проверки

- Backend: **195 passed**, ruff/mypy 0.
- Frontend: Vitest 5, build/tsc 0; Playwright e2e 7/7.
- Load: health 30/5 → p95 76 мс; readyz ~500 мс.
- Security: critical/high нет; pip-audit no known; secrets scan чисто.
- Backup/restore: sha256/users/alembic OK.

## Известные ограничения

- Нет реальных Telegram bot token/LRS endpoint — режимы graceful off.
- Live LLM/voice не проверены без ключей; dev echo/hash-fallback.
- Prod TLS/JWT keys/certs создаются runbook-скриптами; фактический prod
  contour требует `.env.prod`.
- PvP/RAG editor UI — API-only; CSP/axe/hash-lock/egress — backlog.
- LLM/матчи/турниры не в load-smoke; нужен staging-профиль.

## Backlog v0.4 (предложение)

1. Полный LMS-курс/классы mapping, LRS OAuth2.
2. Telegram webhook, teacher-события, алерты failed outbox.
3. PvP UI/зрители, жалобы workflow, сезонные рейтинги.
4. RAG gold-set eval, OCR PDF, CSP/egress allowlist.
5. pip hash-lock/constraints, axe-core в CI, staging load-профиль.
6. Live LLM/voice приёмка на prod.

## Ссылки

- CHANGELOG: `docs/CHANGELOG.md`
- SPEC: `docs/SPEC.md`
- Runbook: `docs/runbooks/release-v0.3.0.md`
- Отчёты: `docs/sprint-reports/`
