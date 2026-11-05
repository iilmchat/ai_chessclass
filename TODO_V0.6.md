# TODO_V0.6.md — План v0.6.0 «Post-release Hardening»

**Статус:** 🔶 В работе (S-75 завершён, S-76…S-79)
**Сводно:** 5 спринтов · **Прогресс: 1/5**
**Цель:** закрыть эксплуатационные разрывы после v0.5.0: реальная доставка
родительских согласий, enforcement, DLQ-операции, OTel-контур и живые
интеграции.

## Спринт S-75 (P0): Consent Enforcement & Email Delivery
**Ветка:** `feat/s-75-consent-enforcement`

**Задачи:**
- [x] SMTP-транспорт `core/email.py` (STARTTLS/SSL/auth, dev-console fallback)
  для verify/reset/parental-consent.
- [x] Enforcement: child/teen без `granted` → 403 для LLM и PDF-отчётов;
  admin/auditor экспорт — по правовому основанию.
- [x] Тесты: SMTP (dev fallback / success / failure), consent gate LLM,
  отчёт; CI/e2e.
- [x] Отчёт `docs/sprint-reports/S-75-2026-11-06.md`, doc-lint/счётчики.

**DoD:**
- [x] Родительское письмо уходит через SMTP при `SMTP_HOST`, иначе в лог.
- [x] LLM/PDF для child/teen без согласия возвращают `parental_consent_required`.
- [x] CI и e2e зелёные; doc-lint 0 failed.

## Спринт S-76 (P1): DLQ Operations & Retention
**Ветка:** `feat/s-76-dlq-operations`

- [ ] retention `failed_jobs` (config/env, cron).
- [ ] Admin API/UI списка failed jobs и ручного retry.
- [ ] Алерт при росте DLQ; тесты, отчёт.

## Спринт S-77 (P1): Observability v0.6
**Ветка:** `feat/s-77-otel-collector`

- [ ] OTel Collector в compose (dev/staging), OTLP endpoint.
- [ ] Дашборды p95/ошибок/trace_id, алерты.
- [ ] Трассировка LLM-провайдеров и arq; тесты, отчёт.

## Спринт S-78 (P2): Integrations & A11y
**Ветка:** `feat/s-78-integrations-a11y`

- [ ] Live LRS-провайдер (OAuth2/mapping) на staging.
- [ ] Live TTS ElevenLabs с fallback/квотой.
- [ ] a11y-обёртка react-chessboard v5 (aria-label клеток).

## Спринт S-79 (P1): Release v0.6.0
**Ветка:** `release/v0.6.0`

- [ ] Load/staging-приёмка с живыми ключами, runbook.
- [ ] Версии/CHANGELOG/release notes, финальный CI/e2e.
- [ ] Тег `v0.6.0`, отчёт S-79.
