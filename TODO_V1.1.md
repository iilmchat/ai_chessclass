# TODO_V1.1.md — План v1.1.0 «Pilot Feedback & Integrations»

**Статус:** 🔶 Активный (цикл v1.1.0 после релиза v1.0.0)
**Сводно:** 4 спринта · **Прогресс: 0/4**
**Цель:** собрать обратную связь пилота в школе, закрыть UX/баги, довести
prod-observability до паритета со staging и подключить live LRS/TTS при
появлении боевых ключей; выпустить **v1.1.0**.

**Контекст:** v1.0.0 «Production Ready» выпущен (тег `v1.0.0`, GHCR,
staging acceptance S-100 8/8 OK); план v1.0.0 — в
[`docs/archive/TODO_V1.0.md`](docs/archive/TODO_V1.0.md).

## S-95: Live LRS/TTS (P1)

**Статус:** ⏸️ Отложен (единственный оставшийся спринт из v1.0.0;
ждёт боевых ключей LRS/ElevenLabs)
**Причина:** без доступа к провайдерам нельзя проверить OAuth2/refresh,
квоты, rate-limit, стоимость TTS и фактическую доставку писем. Контракты
и fallback покрыты тестами (MockTransport), staging SMTP/SPF/DKIM/DMARC
приёмка пройдена.

- [ ] LRS OAuth2: реальный token endpoint, scope, кеш в Redis, refresh при
      401, повтор xAPI PUT; квоты и rate-limit провайдера.
- [ ] TTS: боевой провайдер, graceful fallback при geo/квоте, лимиты
      символов и стоимость в метриках.
- [ ] SMTP/домен: SPF, DKIM, DMARC, return-path/bounce; письмо доходит в
      реальный ящик, не в Spam (см. final-acceptance §1).
- [ ] Live-приёмка staging: `staging-acceptance.ps1`, `llm_smoke.py --mode
      live`, LRS/TTS smoke; отчёт с фактами провайдера.
- **DoD:** live LRS/TTS подтверждены, письмо доставлено, квоты/fallback
  проверены; отчёт `docs/sprint-reports/S-95-YYYY-MM-DD.md`.

## S-102: Feedback & Polish (P1)

**Статус:** ☐ Запланирован (старт — вместе с пилотом в школе)

- [ ] Собрать обратную связь пилота: учителя, ученики, администратор;
      единый журнал `docs/feedback-v1.1.md` (сценарий, ожидание, факт,
      приоритет).
- [ ] Триаж UX/багов: P0 — блокеры занятия, P1 — заметные неудобства,
      P2 — косметика; каждому пункту — решение или явный отказ.
- [ ] Исправить подтверждённые P0/P1: код + тест (Vitest/Playwright или
      backend), без регрессий существующих сценариев.
- [ ] Проверить доступность и тексты новых auth-страниц
      (`/verify-email`, `/reset-password`, `/login`) на живых пользователях.
- **DoD:** журнал обратной связи заполнен, P0/P1 закрыты или
  задокументированы, e2e/CI зелёные; отчёт
  `docs/sprint-reports/S-102-YYYY-MM-DD.md`.

## S-103: Prod-Observability Parity (P2)

**Статус:** ☐ Запланирован (по итогам пилота и решения оператора)

- [ ] Сравнить staging и prod observability: Alertmanager, node-exporter,
      правила алертов, каналы Telegram/email.
- [ ] При необходимости добавить Alertmanager/node-exporter в staging
      (или зафиксировать осознанное отличие и причину).
- [ ] Прогнать `observability-selftest.ps1 -Stack` на полном контуре,
      проверить critical-алерты и маршрутизацию уведомлений.
- [ ] Обновить runbook `docs/runbooks/operations.md` / `staging.md`.
- **DoD:** паритет достигнут или отличие задокументировано, self-test
  зелёный; отчёт `docs/sprint-reports/S-103-YYYY-MM-DD.md`.

## S-104: Release v1.1.0 (P0)

**Статус:** ☐ Запланирован (после S-95/S-102/S-103 или решения владельца)

- [ ] Версия **1.1.0** во всех источниках: `backend/pyproject.toml`,
      `backend/app/__init__.py`, `backend/app/main.py`,
      `frontend/package.json`, `frontend/package-lock.json`,
      `IMAGE_TAG` prod/staging, `.env.*.example`; README/Design.
- [ ] `docs/release-notes-v1.1.0.md`, CHANGELOG `[1.1.0]`, doc-lint:
      `CURRENT_VERSION=1.1.0`, `EXPECTED_VERSION=1.1.0`.
- [ ] README: бейдж и таблица статуса, ссылки на release notes и отчёт
      S-104.
- [ ] Финальные гейты: `ci.ps1`, `e2e.ps1 test`, `smtp-smoke.ps1`,
      `observability-selftest.ps1`, `pip-audit`, doc-lint, аудит
      алфавитов; `git diff --check`.
- [ ] Тег `v1.1.0`, GHCR-образы `v1.1.0`, `docker pull`, отчёт S-104.
- **DoD:** версии и release notes согласованы, тег и образы опубликованы,
  README обновлён; известные ограничения перечислены явно.

---

**Процесс:** ветки `feat/s-1xx-*`; тесты только в Docker (`ci.ps1`,
`e2e.ps1`, `observability-selftest.ps1 -Stack`); doc-lint и аудит алфавитов
перед коммитом; отчёты — `docs/sprint-reports/S-1xx-YYYY-MM-DD.md` по
`docs/RULES.md` §7.
