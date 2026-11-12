# README.md — Хаб документации ChessClass

> **Назначение.** Здесь — карта всех документов проекта и правила их ведения.
> Справочник по архитектуре — в корневом `Design.md` (источник истины);
> здесь только навигация и статусы, без дублирования фактов.

## Карта документов

| Документ | Место | Статус | О чём |
|---|---|---|---|
| `README.md` | корень | ✅ v0.9.0 | Визитка: возможности, быстрый старт, статус, лицензия |
| `Design.md` | корень | ✅ v0.9.0 | Архитектура и решения: 20 разделов, ADR-журнал, инвентарь переноса |
| `TODO_V0.1.md` | корень | ✅ архив | Спринты v0.1.0: S-01…S-29, этапы E-01…E-10 |
| `TODO_V0.2.md` | корень | ✅ v0.2.0 | Спринты v0.2.0: S-30…S-45, этапы E-11…E-16 |
| `TODO_V0.3.md` | корень | ✅ архив | Спринты v0.3.0: S-46…S-57, этапы E-17…E-20 |
| `TODO_V0.4.md` | корень | ✅ завершён | Спринты v0.4.0: S-58…S-69, этапы E-21…E-24 |
| `TODO_V0.5.md` | корень | ✅ завершён | Спринты v0.5.0: S-70…S-74 |
| `TODO_V0.6.md` | корень | ✅ завершён | Спринты v0.6.0: S-75…S-80 |
| `TODO_V0.7.md` | корень | ✅ завершён | Спринты v0.7.0: S-81…S-85 (S-81/S-84 отложены) |
| `TODO_V0.7.1.md` | корень | ✅ завершён | Спринты v0.7.1: S-86…S-89 (tech debt cleanup) |
| `TODO_V0.8.md` | корень | ✅ завершён | Спринты v0.8.0: S-90…S-94; patch v0.8.1 |
| `TODO_V0.9.md` | корень | ✅ активный | Спринты v0.9.0: S-95…S-99 (live, isolation, retention); S-95 отложен |
| `docs/release-notes-v0.9.0.md` | docs/ | ✅ v0.9.0 | Release notes v0.9.0 (isolation, retention, GPU tunnel prep) |
| `docs/release-notes-v0.8.1.md` | docs/ | ✅ v0.8.1 | Release notes v0.8.1 (patch: absolute `-BackupDir`) |
| `docs/release-notes-v0.8.0.md` | docs/ | ✅ v0.8.0 | Release notes v0.8.0 (Production Readiness) |
| `docs/release-notes-v0.7.1.md` | docs/ | ✅ v0.7.1 | Release notes v0.7.1 |
| `docs/release-notes-v0.7.0.md` | docs/ | ✅ v0.7.0 | Release notes v0.7.0 |
| `docs/release-notes-v0.6.0.md` | docs/ | ✅ v0.6.0 | Release notes v0.6.0 |
| `docs/release-notes-v0.5.0.md` | docs/ | ✅ v0.5.0 | Release notes v0.5.0 |
| `docs/privacy-policy.md` | docs/ | ✅ v0.7.0 | Политика конфиденциальности (COPPA/GDPR-K), ред. 1.1 |
| `docs/incident-response.md` | docs/ | ✅ v0.7.0 | План реагирования на инциденты, ред. 1.1 |
| `docs/legal-review-v0.7.md` | docs/ | ✅ S-83/S-89 | Юр-ревью privacy/incident; все 16 вопросов закрыты юристом 2026-11-08 |
| `docs/SPEC.md` | docs/ | ✅ живой (S-33) | Контракты: DDL, API-схемы, JSON-форматы, таблицы промптов/весов |
| `docs/RULES.md` | docs/ | ✅ живой | Процесс: ветки, ревью, отчёт спринта по 7 пунктам, DoD |
| `docs/CHANGELOG.md` | docs/ | ✅ живой (S-60) | Изменения по спринтам (формат Keep a Changelog) |
| `scripts/doc_lint.py` | scripts/ | ✅ S-60 | Doc-lint «правда релиза»: версии, head/счётчики, активный план, стрейл-маркеры |
| `docs/sprint-reports/` | docs/ | по ходу | Отчёты спринтов (по 7 пунктам; шаблон в RULES) |
| `docs/runbooks/` | docs/ | ✅ S-31/S-38/S-58 | Эксплуатация: LLM-шлюз, бэкапы, TLS, инциденты, staging-контур (`staging.md`) |
| `docs/sprint-reports/S-85-2026-11-07.md` | docs/ | ✅ S-85 | Отчёт релиза v0.7.0 (прогоны, тег, риски) |
| `docs/sprint-reports/S-86-2026-11-08.md` | docs/ | ✅ S-86 | Email outbox hardening (SKIP LOCKED, retention) |
| `docs/sprint-reports/S-87-2026-11-08.md` | docs/ | ✅ S-87 | Observability hardening (маскировка, email, disk alert) |
| `docs/sprint-reports/S-88-2026-11-10.md` | docs/ | ✅ S-88 | Certificate rotation & retention ops (cert-check, gauges, runbook) |
| `docs/sprint-reports/S-89-2026-11-10.md` | docs/ | ✅ S-89 | Релиз v0.7.1 (версии, legal closure, тег) |
| `docs/sprint-reports/S-90-2026-11-11.md` | docs/ | ✅ S-90 | Edge/auth hardening (proxy IP, lockout, rate-limit, RS256) |
| `docs/sprint-reports/S-91-2026-11-11.md` | docs/ | ✅ S-91 | Object-level authorization (BOLA fix, cross-tenant tests) |
| `docs/sprint-reports/S-92-2026-11-11.md` | docs/ | ✅ S-92 | CD/registry/observability (GHCR, Sentry, logrotate, multiprocess) |
| `docs/sprint-reports/S-93-2026-11-11.md` | docs/ | ✅ S-93 | SMTP smoke, offsite S3 backups, sandbox hardening |
| `docs/sprint-reports/S-94-2026-11-11.md` | docs/ | ✅ S-94 | Релиз v0.8.0 (версии, release-notes, тег, GHCR) |
| `docs/sprint-reports/v0.8.1-2026-11-11.md` | docs/ | ✅ v0.8.1 | Patch: absolute `-BackupDir` в backup-скриптах |
| `docs/sprint-reports/staging-acceptance-2026-11-11.md` | docs/ | ⏳ операция | Staging Acceptance v0.8.1 (ожидает оператора) |
| `docs/sprint-reports/S-97-2026-11-12.md` | docs/ | ✅ S-97 | Sandbox network isolation (bwrap, seccomp, fallback) |
| `docs/sprint-reports/S-98-2026-11-12.md` | docs/ | ✅ S-98 | Retention email_outbox, legal hold, DSAR erase |
| `docs/sprint-reports/S-96-2026-11-12.md` | docs/ | ✅ S-96 | GPU tunnel (server config, verification, Windows runbook) |
| `docs/sprint-reports/S-99-2026-11-12.md` | docs/ | ✅ S-99 | Релиз v0.9.0 (версии, release-notes, тег, GHCR) |

## Исходные проекты (первоисточники контента)

- `ai-teacher_python` — песочница/levels/LLM-policy/виджеты (перенос: §20.1 Design).
- `ai-chess-annotator` — engine/prompts/policies/PDF (перенос: §20.2 Design).

## Правила ведения

1. **«Один факт — один источник»**: архитектура — в Design, контракты — в
   SPEC, процесс — в RULES, план — в TODO. Дублирование в документах запрещено;
   при расхождении приоритет у Design.
2. Русский язык; идентификаторы кода — EN.
3. Новый факт → сначала Design/приёмка, потом код.
4. Имена копируемых файлов в чеклистах спринтов — справочные; перед стартом
   спринта сверять с фактическим состоянием исходных репо.
