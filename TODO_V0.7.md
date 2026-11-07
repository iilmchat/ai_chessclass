# TODO_V0.7.md — План v0.7.0 «Production Readiness & Legal»

**Статус:** ✅ v0.7.0 (S-82 ✅, S-83 ✅, S-85 ✅; S-81/S-84 ⏸️ отложены)
**Сводно:** 5 спринтов · **Прогресс: 3/5**
**Цель:** Довести платформу до состояния, пригодного для реальной школы: live-приёмка на staging с боевыми ключами, prod-контур observability с Alertmanager, юридическая проверка privacy-policy и GPU-туннель на реальной станции.

## Спринт S-81 (P0): Live Staging Acceptance
**Ветка:** `feat/s-81-live-staging`
**Статус:** ⏸️ Отложен (требуются внешние ключи LRS/ElevenLabs)

**Задачи:**
- [ ] Подключить боевые ключи LRS (OAuth2) и ElevenLabs на staging (внешние credentials в `.env.staging`, не в git).
- [ ] Прогнать xAPI-доставку на реальный LRS-провайдер (например, Learning Locker / Veracity).
- [ ] Прогнать TTS ElevenLabs с реальным ключом (проверить квоты, fallback при 429).
- [ ] Запустить `backend/scripts/load_smoke.py` на staging с p95 в Step Summary.
- [ ] Зафиксировать результаты в `docs/load-profile.md` и `docs/runbooks/staging.md`.

**DoD:**
- [ ] LRS-доставка подтверждена (лог успешного xAPI PUT 200/204).
- [ ] TTS подтверждён (аудио получено, fallback не сработал).
- [ ] Load smoke: p95 API < 500 мс без LLM, < 5 с с LLM.
- [ ] Отчёт: `docs/sprint-reports/S-81-YYYY-MM-DD.md`.

> **Блокер (2026-11-06):** боевые ключи LRS/ElevenLabs во всех env-файлах
> пусты (`LRS_ENABLED=false`, `LRS_KEY/SECRET`, `VOICE_API_KEY` — пусто),
> внешний LRS-провайдер не подключён. S-81 отложен до предоставления
> credentials; вместо него выполнен S-83 (legal/consent/email reliability).

---

## Спринт S-82 (P0): OTel Collector в prod + Alertmanager
**Ветка:** `feat/s-82-prod-observability`

**Задачи:**
- [x] Развернуть OTel Collector + Tempo + Prometheus + Grafana в prod-контуре (с TLS, persistent storage).
- [x] Настроить Alertmanager с доставкой в Telegram (или PagerDuty) для алертов: 5xx-rate, p95, failed_jobs, DLQ.
- [x] Обновить `deploy/observability/` (prod-профиль), `docker-compose.prod.yml`.
- [x] Обновить `docs/runbooks/operations.md`.

**DoD:**
- [x] Алерт «5xx > 5%» доходит до Telegram-чата дежурного.
- [x] Tempo хранит трейсы 7 дней (persistent volume).
- [x] Grafana доступна только через edge-TLS/VPN.
- [x] Отчёт: `docs/sprint-reports/S-82-2026-11-06.md`.

> **Факты реализации:** профиль `observability` в `docker-compose.prod.yml`
> (tempo, otel-collector, prometheus, alertmanager, grafana; volumes
> `chessclass_prod_*`); Tempo `block_retention: 168h`, mTLS на OTLP
> (внутренний CA — `scripts/gen-internal-certs.ps1`); Prometheus retention
> 15 дней, rules → `alertmanager:9093`; Alertmanager рендерит конфиг из
> шаблона (Telegram `telegram_configs`, route critical/warning, inhibit);
> Grafana — обязательный пароль, anonymous off, loopback + edge `/grafana/`.
> Проверки: `scripts/observability-selftest.ps1 [-Stack]`.

---

## Спринт S-83 (P0): Legal & Privacy Review
**Ветка:** `feat/s-83-legal`

**Задачи:**
- [x] Провести внутреннюю юридическую проверку `docs/privacy-policy.md` и `docs/incident-response.md` (юрисдикции РФ/ЕС/США).
- [x] Обновить контакты (privacy@/security@), реквизиты, сроки уведомления (GDPR 72 ч, 152-ФЗ).
- [x] Добавить consent enforcement v0.6.1: подтверждение возраста учителем (teacher confirmation of student age_group).
- [x] Добавить SMTP retry (очередь писем) для parental consent.

**DoD:**
- [x] Документы прошли проверку (или зафиксированы открытые вопросы с юристом).
- [x] Учитель может подтвердить возраст ученика (эндпоинт + UI).
- [x] SMTP retry работает (тест).
- [x] Отчёт: `docs/sprint-reports/S-83-2026-11-06.md`.

---

## Спринт S-84 (P1): GPU Tunnel on Real Station
**Ветка:** `feat/s-84-gpu-tunnel`
**Статус:** ⏸️ Отложен (требуется физическая станция RTX 3060 + LM Studio)

**Задачи:**
- [ ] Настроить обратный SSH-туннель на реальной Windows-станции (RTX 3060 + LM Studio).
- [ ] Подключить `LLM_LOCAL_BASE_URL` на staging к туннелю.
- [ ] Настроить мониторинг reconnect (Scheduled Task + алерт при падении туннеля).
- [ ] Прогнать нагрузочный тест на L1/L2 маршруты через локальный GPU (сравнить latency и стоимость с облаком).

**DoD:**
- [ ] Запрос к `/chess/insight` на staging идёт через GPU (в `llm_calls.model_used = "lmstudio"`).
- [ ] При падении туннеля CB переключает на cloud (тест).
- [ ] Замеры latency и стоимости в `docs/load-profile.md`.
- [ ] Отчёт: `docs/sprint-reports/S-84-YYYY-MM-DD.md`.

---

## Спринт S-85 (P0): Release v0.7.0
**Ветка:** `release/v0.7.0`
**Статус:** ✅ Завершён (2026-11-07)

**Задачи:**
- [x] Обновить версии до 0.7.0, счётчики, `docs/release-notes-v0.7.0.md`.
- [x] Финальный `ci.ps1` + `e2e.ps1` + staging smoke.
- [x] Тег `v0.7.0`, squash-merge в main.

**DoD:**
- [x] Тег `v0.7.0` запушен.
- [x] Отчёт: `docs/sprint-reports/S-85-2026-11-07.md`.

> **Факты релиза:** версия 0.7.0 во всех источниках (backend/frontend,
> IMAGE_TAG prod/staging); release-notes v0.7.0 и CHANGELOG `[0.7.0]`;
> финальные прогоны `ci.ps1`, `e2e.ps1`, Vitest/build, `observability-selftest`
> и `docker compose config -q` — зелёные. S-81/S-84 остаются отложенными:
> live LRS/TTS не проверены без боевых ключей, GPU-туннель — без станции.

---

> **S-86…S-89 не входят в v0.7.0**: цикл v0.7.1 «Tech Debt Cleanup»
> описан в `TODO_V0.7.1.md` (S-86 email outbox hardening — SKIP LOCKED и
> retention; S-87 observability hardening; S-88 ротация сертификатов;
> S-89 релиз v0.7.1).
