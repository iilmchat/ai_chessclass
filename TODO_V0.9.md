# TODO_V0.9.md — Цикл v0.9.0 <Live, Isolation & Retention>

**Статус:** 🔶 В работе (S-95…S-98 впереди; S-99 — релиз)
**Сводно:** 5 спринтов · **Прогресс: 0/5**
**Цель:** закрыть операционные долги после v0.8.1: live-провайдеры,
изоляция песочницы, retention/legal hold и релиз v0.9.0.

**Порядок:** S-97 и S-98 можно делать сразу и параллельно; S-95/S-96 ждут
внешних ресурсов; S-99 — после закрытия доступных спринтов.

## S-95: Live LRS/TTS (S-81) (P1)

**Статус:** ⏸️ Отложен (требуются внешние ключи/станция)
**Причина:** нет боевых ключей LRS/ElevenLabs и доступа к провайдеру.

- [ ] LRS OAuth2: реальный token endpoint, scope, кеш в Redis, refresh при
      401, повтор xAPI PUT; квоты и rate-limit провайдера.
- [ ] TTS: боевой провайдер, graceful fallback при geo/квоте, лимиты
      символов и стоимость в метриках.
- [ ] SMTP/домен: SPF, DKIM, DMARC, return-path/bounce; письмо доходит в
      реальный ящик, не в Spam.
- [ ] Live-приёмка staging: `staging-acceptance.ps1`, `llm_smoke.py --mode
      live`, LRS/TTS smoke; отчёт с фактами провайдера.
- **DoD:** live LRS/TTS подтверждены, письмо доставлено, квоты/fallback
  проверены; отчёт `docs/sprint-reports/S-95-YYYY-MM-DD.md`.

## S-96: GPU Tunnel (S-84) (P2)

**Статус:** ⏸️ Отложен (требуются внешние ключи/станция)
**Причина:** нет физической станции RTX 3060 + LM Studio.

- [ ] Поднять LM Studio на станции с RTX 3060, выбрать модель и контекст.
- [ ] Безопасный туннель до staging (WireGuard/SSH, allowlist, auth);
      никаких публичных портов модели.
- [ ] End-to-end: LLM-запрос через туннель, таймауты/ретраи, fallback на
      RouterAI/echo при недоступности.
- [ ] Метрики: latency, ошибки, стоимость; smoke и runbook.
- **DoD:** запрос доходит до станции и возвращает ответ; fallback проверен;
  доступ не шире staging; отчёт `docs/sprint-reports/S-96-YYYY-MM-DD.md`.

## S-97: Sandbox Network Isolation (P0)

**Статус:** ☐ Запланирован
**Цель:** убрать opt-in `unshare -n` и привилегии из worker.

- [ ] Отдельный sandbox-контейнер с `network_mode: none`, non-root,
      read-only rootfs, без capabilities, лимиты CPU/памяти/pids.
- [ ] `sandbox/executor.py`: запуск задания в sandbox-контейнере (или
      документированный эквивалент), таймаут/kill, сбор stdout/stderr.
- [ ] Compose: сервис `sandbox`/`worker-sandbox` без доступа к БД/Redis;
      сеть только между API/worker и sandbox (или `none` + stdin/stdout).
- [ ] Тест-матрица атак: network (`socket`, `__import__`), filesystem
      (`/etc/passwd`), CPU/память, fork/pids; отсутствие регрессий.
- [ ] Runbook: диагностика sandbox, лимиты, ротация образа; Design §13.2 и
      SPEC §7.
- **DoD:** worker не требует root/CAP_SYS_ADMIN; network-атаки блокируются
  на уровне контейнера; 5+ тестов; runbook обновлён.

## S-98: Retention & Legal Hold (P1)

**Статус:** ☐ Запланирован
**Цель:** PII в `email_outbox`, legal hold и удаление по запросу субъекта.

- [ ] Retention `email_outbox`: TTL для `sent`/`failed`, архивирование
      метаданных, удаление body с PII; настраиваемые сроки.
- [ ] Legal hold: флаг/таблица удержания по пользователю/делу; retention не
      удаляет объекты под hold; аудит изменений.
- [ ] DSAR-удаление: удаление/анонимизация профиля, outbox, вложений,
      связанных записей; отчёт об исполнении.
- [ ] Метрики: `chessclass_email_outbox_pending_total`,
      `..._oldest_pending_age_seconds`, retention archived/deleted, hold count.
- [ ] Тесты: hold блокирует удаление, DSAR удаляет PII, retention не трогает
      hold; миграция и runbook.
- **DoD:** policy применяется идемпотентно; hold/DSAR проверены тестами;
  метрики/алерты; отчёт `docs/sprint-reports/S-98-YYYY-MM-DD.md`.

## S-99: Release v0.9.0 (P0)

**Статус:** ☐ Запланирован

- [ ] Версия **0.9.0** во всех источниках: `backend/pyproject.toml`,
      `backend/app/__init__.py`, `backend/app/main.py`,
      `frontend/package.json`, `frontend/package-lock.json`,
      `IMAGE_TAG` prod/staging, `.env.*.example`; README/Design.
- [ ] `docs/release-notes-v0.9.0.md`, CHANGELOG `[0.9.0]`, doc-lint:
      `EXPECTED_VERSION=0.9.0`, прогресс `5/5`.
- [ ] Финальные гейты: `ci.ps1`, `e2e.ps1 test`, `smtp-smoke.ps1`,
      `observability-selftest.ps1 -Stack`, staging acceptance, pip-audit,
      doc-lint; аудит алфавитов.
- [ ] Тег `v0.9.0`, GHCR-образы `v0.9.0`, `docker pull`, отчёт S-99.
- **DoD:** все доступные спринты закрыты (S-95/S-96 могут остаться
  отложенными с явной пометкой), тег и образы опубликованы.

---

**Процесс:** ветки `feat/s-9x-*`; тесты только в Docker (`ci.ps1`,
`e2e.ps1`, `observability-selftest.ps1 -Stack`); doc-lint и аудит алфавитов
перед коммитом; отчёты — `docs/sprint-reports/S-9x-YYYY-MM-DD.md` по
`docs/RULES.md` §7.
