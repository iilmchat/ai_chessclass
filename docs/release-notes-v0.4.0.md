# Release Notes — ChessClass v0.4.0

**Дата:** 2026-11-04 · Спринты S-58…S-69 (12/12), этапы E-21…E-24 ✅.

## Новое в v0.4.0

### Инфраструктура и безопасность
- **Staging-контур (S-58)** — prod-parity stack (порты ADR-014), CORS
  allowlist, runbook; предупреждение о localhost-origin в staging/prod.
- **CSP и egress-allowlist (S-61)** — CSP в web-nginx (enforce; staging
  report-only), egress-гейт на все исходящие httpx-клиенты
  (`502 egress_blocked` при нарушении policy), `env_ignore_empty`.
- **Hash-lock сборка (S-62)** — `requirements.lock` (pip-compile
  --generate-hashes), Docker `--require-hashes`, SHA256-pin Stockfish.
- **CI-ворота (S-63)** — pip-audit, axe-core, backup→restore smoke,
  gitleaks, docker-build; недельный load-cron с p95 в Summary.
- **Наблюдаемость (S-68)** — алерты failed Telegram-outbox и failed
  LRS-deliveries в `/ops`.

### Продукт
- **RAG-редактор (S-64)** — UI `/rag`: версии/лицензии/публикация/откат/
  импорт/поиск; gold-set eval **21 кейс** (baseline/hybrid в панели).
- **PvP-жалобы (S-65)** — `/pvp` (комнаты/quick-match/SSE/реплей) и
  `/complaints` (review-воркфлоу для teacher/admin).
- **A11y-гейт (S-66)** — axe-core на 20 маршрутов (0 critical/serious),
  aria-live/контраст/мобильная адаптация; UI-e2e → **14 сценариев**.
- **LRS OAuth2 + LMS-mapping (S-67)** — client_credentials + токен-кэш
  (Basic-fallback), курсы LMS и привязка классов, админ-панель в `/ops`;
  activity id skill-объектов — через activity_ref курса.
- **Telegram webhook (S-68)** — `/start <код>`/`/stop` через секретный
  webhook, long-poll fallback (worker-cron), teacher-события
  (сдача/турнир/жалоба учителям классов).

## Числа
- Backend: **235 collected** (232 passed + 3 skipped); ruff/mypy 0.
- Frontend: Vitest 5, tsc 0, build ok; UI-e2e 14 passed.
- Alembic head `0030_s67_lms_oauth` (30 миграций).
- Целевой axe/стейндж-прогон: 0 critical/serious; локальный e2e полный
  прогон и CI e2e — см. runbook §4.

## Известные ограничения (backlog v0.5)
- **Live TTS ElevenLabs** — гео-блок из РФ (S-59); альтернативный
  провайдер — backlog.
- **react-chessboard v5** — клетки доски без aria-label (third-party);
  исключены из axe-гейта, апгрейд — backlog.
- **Live LRS-провайдер** — OAuth2 и mapping приняты на MockTransport и
  unit/e2e-контуре; живой приём на staging требует конфигурации IdP.
- **Load/prod-приёмка с живыми ключами** — выполняется на staging-стенде
  (load.yml cron + runbook §5); не воспроизводимо в dev.

## Обновление
- `git fetch --tags && git checkout v0.4.0`
- `IMAGE_TAG=0.4.0`; миграции до head 0030 запускаются compose-гейтом.
- Новые env: `LRS_OAUTH_*`, `TELEGRAM_WEBHOOK_SECRET`,
  `TELEGRAM_POLL_ENABLED` — шаблоны в `.env.*.example`.
