# TODO_V0.8.md — План v0.8.0 «Production Readiness»

**Статус:** 🔶 В работе (S-90 ✅; S-91…S-94 впереди)
**Сводно:** 5 спринтов · **Прогресс: 1/5**
**Цель:** Закрыть блокеры DevOps-аудита для выхода в production (пилот в школе).

## S-90: Edge & Auth Hardening (P0)
**Статус:** ✅ Завершён (2026-11-11)

- [x] Реальный IP за прокси: настроить `ProxyHeadersMiddleware` (FastAPI) и передачу `X-Forwarded-For` от edge/nginx.
- [x] Заменить глобальный auth-lockout на per-account (per-user) lockout + edge rate-limit (защита от DoS).
- [x] Отключить `JWT_LEGACY_HS256=true` (полный переход на RS256/JWKS).
- **DoD:** ✅ Тест на per-account lockout; тест на реальный IP; edge smoke 11-й = 429.

## S-91: Object-Level Authorization (P0)
- [ ] Проверка владения для `/reports/pdf/{id}` и `/audit/logs` (учитель видит только своих учеников, аудитор — только свой scope).
- [ ] Кросс-тенантные тесты API (`test_authz_cross_tenant.py`), аналогичные RLS-тестам S-72, но на уровне API.
- **DoD:** Учитель А получает 403 при запросе PDF учителя Б; тесты покрывают все эндпоинты с `{id}`.

## S-92: CD, Registry & Observability (P1)
- [ ] GitHub Container Registry (GHCR): публикация образов `chessclass/backend` и `chessclass/frontend`.
- [ ] Error-tracking: Sentry (или self-hosted GlitchTip) для API и frontend.
- [ ] Ротация логов (logrotate) для uvicorn и arq.
- [ ] Исправить метрики per-process: Prometheus multiprocess mode или OTel spanmetrics.
- **DoD:** Образы публикуются в GHCR; Sentry ловит тестовую ошибку; logrotate настроен.

## S-93: SMTP, Backups & Sandbox (P0)
- [ ] Настроить SMTP в prod (обязательно для email-верификации).
- [ ] Offsite-бэкапы: S3 (или совместимое) + шифрование + алерт + авто-тест restore.
- [ ] Усилить песочницу: CPU-rlimit, network namespace, non-root user для worker.
- **DoD:** SMTP работает (письмо доходит); бэкап уходит в S3 и восстанавливается; песочница проходит тест-матрицу атак.

## S-94: Release v0.8.0 (Production Ready)
- [ ] Финальные прогоны, тег `v0.8.0`, release-notes.
- **DoD:** Все гейты зелёные, тег запушен.

---

**Процесс:** ветки `feat/s-9x-…`, только Docker-прогоны (`ci.ps1`,
`e2e.ps1`, `observability-selftest.ps1 -Stack`), doc-lint и аудит алфавитов
перед коммитом; отчёты — `docs/sprint-reports/S-9x-YYYY-MM-DD.md`.
