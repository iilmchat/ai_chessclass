# TODO_V0.7.1.md — План v0.7.1 «Tech Debt Cleanup»

**Статус:** 🔶 В работе (S-86 ✅; S-87…S-89 впереди)
**Сводно:** 4 спринта · **Прогресс: 1/4**
**Цель:** Закрыть техдолг, накопленный в v0.7.0: надёжность email outbox при параллельных воркерах, retention писем, маскировка секретов в логах observability, ротация внутренних сертификатов и релиз v0.7.1.

## Спринт S-86 (P0): Email Outbox Hardening
**Ветка:** `feat/s-86-email-outbox`
**Статус:** ✅ Завершён (2026-11-08)

**Задачи:**
- [x] `FOR UPDATE SKIP LOCKED` в `deliver_pending` — ровно один воркер на письмо.
- [x] Retention `EMAIL_OUTBOX_RETENTION_DAYS=30`: gzip-архив и удаление `sent`/`failed`.
- [x] Проверить индекс `(status, next_attempt_at)`; миграция не нужна — есть с `0035`.
- [x] Тесты параллельной доставки и retention; SPEC/Design/CHANGELOG.

**DoD:**
- [x] Два параллельных `deliver_pending` не отправляют письмо дважды.
- [x] Retention архивирует и удаляет терминальные строки, pending не трогает.
- [x] Отчёт: `docs/sprint-reports/S-86-2026-11-08.md`.

---

## Спринт S-87 (P0): Observability Hardening
**Ветка:** `feat/s-87-observability-hardening`

**Задачи:**
- [ ] Маскировать Telegram bot token и `Authorization` в логах Alertmanager/collector.
- [ ] Добавить второй receiver (email/webhook) и проверить маршрут critical/warning.
- [ ] Алерт «диск заполнен» (prometheus rule + runbook).
- [ ] Обновить `docs/runbooks/operations.md` и `scripts/observability-selftest.ps1`.

**DoD:**
- [ ] В логах нет raw-токенов (тест/греп).
- [ ] Второй receiver получает тестовый алерт.
- [ ] Алерт по диску срабатывает на пороге.
- [ ] Отчёт: `docs/sprint-reports/S-87-YYYY-MM-DD.md`.

---

## Спринт S-88 (P1): Certificate Rotation & Retention Ops
**Ветка:** `feat/s-88-cert-rotation`
**Статус:** черновик (текст плана уточняется)

**Задачи:**
- [ ] Ротация внутренних сертификатов Tempo/collector с проверкой срока и `-Force`.
- [ ] Мониторинг parked/failed `email_outbox` и целостности gzip-архива.
- [ ] Runbook: ротация без простоя, откат.
- [ ] Отчёт: `docs/sprint-reports/S-88-YYYY-MM-DD.md`.

---

## Спринт S-89 (P1): Release v0.7.1
**Ветка:** `release/v0.7.1`

**Задачи:**
- [ ] Версия 0.7.1 во всех источниках, release-notes, CHANGELOG.
- [ ] Финальные `ci.ps1` + `e2e.ps1`, observability-selftest, config -q.
- [ ] Тег `v0.7.1`, squash-merge в `main`.

**DoD:**
- [ ] Тег `v0.7.1` запушен.
- [ ] Отчёт: `docs/sprint-reports/S-89-YYYY-MM-DD.md`.
