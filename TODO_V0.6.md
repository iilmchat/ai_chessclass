# TODO_V0.6.md — План v0.6.0 «Post-release Hardening»

**Статус:** ✅ v0.6.0 (S-75…S-80 завершены)
**Сводно:** 6 спринтов · **Прогресс: 6/6**
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

- [x] retention `failed_jobs` (config/env, cron).
- [x] Admin API/UI списка failed jobs и ручного retry.
- [x] Алерт при росте DLQ; тесты, отчёт
  `docs/sprint-reports/S-76-2026-11-06.md`.

## Спринт S-77 (P1): Observability v0.6
**Ветка:** `feat/s-77-otel-collector`

- [x] OTel Collector в compose (dev/staging), OTLP endpoint.
- [x] Дашборды p95/ошибок/trace_id, алерты.
- [x] Трассировка LLM-провайдеров и arq; тесты, отчёт
  `docs/sprint-reports/S-77-2026-11-06.md`.

## Спринт S-78 (P1): Infrastructure: GPU Backend Support
**Ветка:** `feat/s-78-gpu-backend`

- [x] `LLM_LOCAL_API_KEY` в config/env; отдельный ключ LM Studio.
- [x] `OpenAICompatProvider` выбирает локальный ключ для local base_url;
  gateway передаёт ключ в `get_local_provider`.
- [x] Runbook: обратный SSH-туннель GPU (RTX 3060) + LM Studio.
- [x] Тесты Authorization header; отчёт
  `docs/sprint-reports/S-78-2026-11-06.md`.

## Спринт S-79 (P2): Integrations & A11y
**Ветка:** `feat/s-79-integrations-a11y`

- [x] Live LRS-провайдер (OAuth2 + Redis-кэш + 401 refresh) на staging.
- [x] Live TTS ElevenLabs с fallback/квотой (`X-Voice-Fallback: text`).
- [x] a11y-обёртка react-chessboard v5 (aria-label клеток) + e2e.
- [x] Отчёт `docs/sprint-reports/S-79-2026-11-06.md`.

## Спринт S-80 (P1): Release v0.6.0
**Ветка:** `release/v0.6.0`

- [x] Staging config smoke (`config -q`); live-ключи — post-release v0.7.
- [x] Версии/CHANGELOG/release notes, финальный CI/e2e.
- [x] Тег `v0.6.0`, отчёт S-80.
