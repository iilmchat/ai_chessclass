# TODO_V0.5.md — План v0.5.0 «Hardening & Compliance»

**Статус:** 🔶 В работе (S-70…S-74)
**Цель:** Закрыть разрывы до уровня Production-Grade (Best Practices): отказоустойчивость LLM, защита от OWASP LLM Top 10, изоляция данных на уровне БД (P0), а также надежность воркеров, трассировка и EdTech-compliance (P1).

## Спринт S-70 (P0): LLM Gateway Resilience
**Ветка:** `feat/s-70-llm-resilience`

**Задачи:**
- [ ] Внедрить Circuit Breaker per route в `llm/gateway.py` (состояния CLOSED → OPEN → HALF_OPEN в Redis).
- [ ] Добавить token-aware rate limits (не только RPM, но и лимит на токены в минуту).
- [ ] Реализовать retry с экспоненциальным backoff и jitter.
- [ ] Разделить `fallback_from` в `llm_calls` на `failover` (ошибка провайдера) и `fallback` (квота/отключен).
- [ ] Тесты: state-machine unit-тесты + интеграционный тест «провайдер упал → OPEN → HALF_OPEN → восстановление».

**DoD:**
- [ ] При падении RouterAI шлюз не «долбит» его, а переключается на LM Studio/Echo и фиксирует состояние в Redis.
- [ ] CI зелёный. Отчёт: `docs/sprint-reports/S-70-YYYY-MM-DD.md`.

---

## Спринт S-71 (P0): OWASP LLM Top 10 Hardening & CI Eval
**Ветка:** `feat/s-71-owasp-llm`

**Задачи:**
- [ ] Добавить adversarial-тест-матрицу для `llm/prompts/` (prompt injection, system prompt leakage, improper output handling).
- [ ] Внедрить instruction isolation в `builder.py`: структурное разделение trusted/untrusted контента.
- [ ] Добавить provenance tagging для RAG-фрагментов и output grounding для `chess_lab`/`anticheat` (проверка, что LLM не меняет факты SF).
- [ ] Добавить в `.github/workflows/ci.yml` запуск `chess_rag_eval.py` и `rag_gold_check.py` как блокирующий гейт.

**DoD:**
- [ ] Adversarial-тесты проходят (модель не поддается инъекциям).
- [ ] CI падает при MISS в RAG-eval.
- [ ] CI зелёный. Отчёт: `docs/sprint-reports/S-71-YYYY-MM-DD.md`.

---

## Спринт S-72 (P0): Multi-tenant DB Isolation (RLS)
**Ветка:** `feat/s-72-multi-tenant`

**Задачи:**
- [x] Обойтись без денормализации `class_id`: принадлежность выводится через
  `class_members` → `classes.teacher_id` (контракт S-72).
- [x] Настроить PostgreSQL Row-Level Security (RLS) политики для `bot_stats`,
  `cognitive_skill_events`, `anticheat_flags`.
- [x] Использовать существующие JWT-клеймы `sub`/`role` (отдельный `tenant_id`
  не нужен: политика строит классы по `user_id` учителя).
- [x] Обновить `core/db.py`: `SET LOCAL`-контекст `app.current_user_id` /
  `app.current_user_role` на соединении из пула + `SET LOCAL ROLE chess_app`.
- [x] Прокинуть `user_id`/`role` через HTTP-middleware и аргументы arq-задач.
- [x] Тест на уровне БД: «учитель школы A не видит данные школы B» (прямой SQL-запрос без фильтров в коде).

**DoD:**
- [x] Миграция безопасна для существующих данных (без backfill, `user_id NOT NULL`, `ondelete` не меняется).
- [x] Тест RLS проходит и падает, если RLS отключить (проверка `relrowsecurity`/`relforcerowsecurity`).
- [x] CI зелёный. `doc_lint` обновлён. Отчёт: `docs/sprint-reports/S-72-2026-11-05.md`.

---

## Спринт S-73 (P1): Async Reliability & Tracing
**Ветка:** `feat/s-73-async-otel`

**Задачи:**
- [ ] arq idempotency: добавить `_job_id` для `run_match` и `analyze_game`.
- [ ] arq DLQ: добавить `max_tries`, `on_job_failure` в `WorkerSettings` и таблицу `failed_jobs`.
- [ ] OTel tracing: внедрить OpenTelemetry SDK, связать `trace_id` из API → arq → LLM (сохранить в `llm_calls`).
- [ ] Обновить `requirements.lock` (`pip-audit`).

**DoD:**
- [ ] Повторный HTTP-запрос матча не создаёт дубль.
- [ ] Упавшая задача фиксируется в `failed_jobs`.
- [ ] Сквозной `trace_id` виден в логах для HTTP и arq-задач.
- [ ] CI зелёный. Отчёт: `docs/sprint-reports/S-73-YYYY-MM-DD.md`.

---

## Спринт S-74 (P1): Compliance & Release v0.5.0
**Ветка:** `release/v0.5.0`

**Задачи:**
- [ ] Parental consent workflow: спроектировать эндпоинт и UI для подтверждения согласия (COPPA/GDPR-K).
- [ ] Создать `docs/privacy-policy.md` и `docs/incident-response.md`.
- [ ] Финальный прогон: `scripts/ci.ps1`, `scripts/e2e.ps1`.
- [ ] Обновить версии в `README.md`, `Design.md`, `CHANGELOG.md`.
- [ ] Сформировать `docs/release-notes-v0.5.0.md`.

**DoD:**
- [ ] Тег `v0.5.0` на GitHub. CI зелёный.
- [ ] `doc_lint.py` обновляет счётчики без ошибок.
- [ ] Отчёт: `docs/sprint-reports/S-74-YYYY-MM-DD.md`.