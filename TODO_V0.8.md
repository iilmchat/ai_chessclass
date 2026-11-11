# TODO_V0.8.md — План v0.8.0 «Production Readiness»

**Статус:** ✅ Завершён (S-90…S-94 ✅; релиз v0.8.0)
**Сводно:** 5 спринтов · **Прогресс: 5/5**
**Цель:** Закрыть блокеры DevOps-аудита для выхода в production (пилот в школе).

## S-90: Edge & Auth Hardening (P0)
**Статус:** ✅ Завершён (2026-11-11)

- [x] Реальный IP за прокси: настроить `ProxyHeadersMiddleware` (FastAPI) и передачу `X-Forwarded-For` от edge/nginx.
- [x] Заменить глобальный auth-lockout на per-account (per-user) lockout + edge rate-limit (защита от DoS).
- [x] Отключить `JWT_LEGACY_HS256=true` (полный переход на RS256/JWKS).
- **DoD:** ✅ Тест на per-account lockout; тест на реальный IP; edge smoke 11-й = 429.

## S-91: Object-Level Authorization (P0)
**Статус:** ✅ Завершён (2026-11-11)

- [x] Проверка владения для `/reports/pdf/{id}` и `/audit/logs` (учитель видит только своих учеников, аудитор — только свой scope).
- [x] Кросс-тенантные тесты API (`test_authz_cross_tenant.py`), аналогичные RLS-тестам S-72, но на уровне API.
- **DoD:** ✅ Учитель А получает 403 при запросе PDF учителя Б; тесты покрывают все эндпоинты с `{id}`; RS256-токены.

## S-92: CD, Registry & Observability (P1)
**Статус:** ✅ Завершён (2026-11-11)

- [x] GitHub Container Registry (GHCR): публикация образов `chessclass/backend` и `chessclass/frontend`.
- [x] Error-tracking: Sentry (или self-hosted GlitchTip) для API и frontend.
- [x] Ротация логов (logrotate) для uvicorn и arq.
- [x] Исправить метрики per-process: Prometheus multiprocess mode или OTel spanmetrics.
- **DoD:** ✅ Образы публикуются в GHCR (workflow); Sentry-старт проверен с фиктивным DSN; Docker json-file + logrotate; multiprocess smoke с 2 воркерами.

## S-93: SMTP, Backups & Sandbox (P0)
**Статус:** ✅ Завершён (2026-11-11)

- [x] Настроить SMTP в prod (обязательно для email-верификации).
- [x] Offsite-бэкапы: S3 (или совместимое) + шифрование + алерт + авто-тест restore.
- [x] Усилить песочницу: CPU-rlimit, network namespace, non-root user для worker.
- **DoD:** ✅ SMTP smoke (verification/password-reset) + STARTTLS/SSL tests; бэкап S3Mock→restore (users=15/alembic); sandbox 5+ attack tests; alerts 10 правил.

## S-94: Release v0.8.0 (Production Ready)
**Статус:** ✅ Завершён (2026-11-11)

- [x] Версии **0.8.0** во всех источниках (backend/frontend, `IMAGE_TAG` prod/staging и env-examples), README/Design.
- [x] `docs/release-notes-v0.8.0.md` и секция CHANGELOG `[0.8.0] - 2026-11-11`.
- [x] Финальные прогоны: `ci.ps1`, `e2e.ps1 test`, `smtp-smoke.ps1`, `backup-restore-test.ps1`, `observability-selftest.ps1 -Stack`, pip-audit, doc-lint.
- [x] Тег `v0.8.0` запушен, GHCR-образы `v0.8.0` опубликованы и проверены `docker pull`.
- **DoD:** ✅ Все гейты зелёные, тег запушен.

---

**Процесс:** ветки `feat/s-9x-…`, только Docker-прогоны (`ci.ps1`,
`e2e.ps1`, `observability-selftest.ps1 -Stack`), doc-lint и аудит алфавитов
перед коммитом; отчёты — `docs/sprint-reports/S-9x-YYYY-MM-DD.md`.
