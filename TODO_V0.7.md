# TODO_V0.7.md — План v0.7.0 «Production Readiness & Legal»

**Статус:** 🔶 В работе (S-81…S-85)
**Цель:** Довести платформу до состояния, пригодного для реальной школы: live-приёмка на staging с боевыми ключами, prod-контур observability с Alertmanager, юридическая проверка privacy-policy и GPU-туннель на реальной станции.

## Спринт S-81 (P0): Live Staging Acceptance
**Ветка:** `feat/s-81-live-staging`

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

---

## Спринт S-82 (P0): OTel Collector в prod + Alertmanager
**Ветка:** `feat/s-82-prod-observability`

**Задачи:**
- [ ] Развернуть OTel Collector + Tempo + Prometheus + Grafana в prod-контуре (с TLS, persistent storage).
- [ ] Настроить Alertmanager с доставкой в Telegram (или PagerDuty) для алертов: 5xx-rate, p95, failed_jobs, DLQ.
- [ ] Обновить `deploy/observability/` (prod-профиль), `docker-compose.prod.yml`.
- [ ] Обновить `docs/runbooks/operations.md`.

**DoD:**
- [ ] Алерт «5xx > 5%» доходит до Telegram-чата дежурного.
- [ ] Tempo хранит трейсы 7 дней (persistent volume).
- [ ] Grafana доступна только через edge-TLS/VPN.
- [ ] Отчёт: `docs/sprint-reports/S-82-YYYY-MM-DD.md`.

---

## Спринт S-83 (P0): Legal & Privacy Review
**Ветка:** `feat/s-83-legal`

**Задачи:**
- [ ] Провести внутреннюю юридическую проверку `docs/privacy-policy.md` и `docs/incident-response.md` (юрисдикции РФ/ЕС/США).
- [ ] Обновить контакты (privacy@/security@), реквизиты, сроки уведомления (GDPR 72 ч, 152-ФЗ).
- [ ] Добавить consent enforcement v0.6.1: подтверждение возраста учителем (teacher confirmation of student age_group).
- [ ] Добавить SMTP retry (очередь писем) для parental consent.

**DoD:**
- [ ] Документы прошли проверку (или зафиксированы открытые вопросы с юристом).
- [ ] Учитель может подтвердить возраст ученика (эндпоинт + UI).
- [ ] SMTP retry работает (тест).
- [ ] Отчёт: `docs/sprint-reports/S-83-YYYY-MM-DD.md`.

---

## Спринт S-84 (P1): GPU Tunnel on Real Station
**Ветка:** `feat/s-84-gpu-tunnel`

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

**Задачи:**
- [ ] Обновить версии до 0.7.0, счётчики, `docs/release-notes-v0.7.0.md`.
- [ ] Финальный `ci.ps1` + `e2e.ps1` + staging smoke.
- [ ] Тег `v0.7.0`, squash-merge в main.

**DoD:**
- [ ] Тег `v0.7.0` запушен.
- [ ] Отчёт: `docs/sprint-reports/S-85-YYYY-MM-DD.md`.