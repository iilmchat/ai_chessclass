# TODO_V0.9.md — Цикл v0.9.0 <Live, Isolation & Retention>

**Статус:** ✅ Завершён (S-95 отложен; S-96…S-99 ✅; релиз v0.9.0)
**Сводно:** 5 спринтов · **Прогресс: 4/5**
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

**Статус:** ✅ Завершён (2026-11-12); live-проверка — оператор станции
**Станция:** Windows, RTX 3060 12 GB, 32 GB RAM, Xeon E5-2690 v3,
LM Studio + Qwen-7B.

- [x] LM Studio на станции: Qwen2.5-7B-Instruct, Q4_K_M, Serve on Local
      Network, Require Auth; инструкция runbook §6.
- [x] Безопасный reverse SSH-туннель (`GatewayPorts clientspecified`,
      bind 172.18.0.1:8035, ключ, Scheduled Task); `wg-gpu-tunnel.ps1`.
- [x] Сервер: `LLM_LOCAL_FALLBACK/BASE_URL/MODEL/API_KEY` в prod/staging;
      `test-gpu-tunnel.ps1` проверяет models/chat/latency/tokens-per-second.
- [x] Fallback cloud → local → echo и breaker local проверены тестами;
      runbook §6, Design §8.4, SPEC §6.4.
- [ ] Live-запрос через физическую станцию (ожидает оператора).
- **DoD:** сервер/скрипты/тесты готовы; live GPU подтверждается оператором
  через `test-gpu-tunnel.ps1`; отчёт `docs/sprint-reports/S-96-2026-11-12.md`.

## S-97: Sandbox Network Isolation (P0)

**Статус:** ✅ Завершён (2026-11-12)
**Цель:** убрать opt-in `unshare -n` и привилегии из worker.

- [x] `bwrap --unshare-net` по умолчанию (uid 1000); `/usr`, `/usr/local`,
      `/lib`, `/lib64`, `backend` — read-only bind, `/tmp` — tmpfs,
      `--die-with-parent`.
- [x] `SANDBOX_NETWORK_ISOLATION=true`, `SANDBOX_NETWORK_BACKEND=auto`
      (`auto|bwrap|unshare|none`); fallback `unshare`/none с warning.
- [x] `deploy/seccomp-sandbox.json`: Docker default + namespace/mount
      syscalls для bwrap без `--privileged`/CAP_SYS_ADMIN; compose
      `security_opt` для api/worker/match.
- [x] `sandbox/executor.py`: `network_isolation_enforced`,
      `network_backend`, fallback и маппинг 128+signal (bwrap).
- [x] Тесты: bwrap probe, `socket.connect` → отказ, fallback/warning,
      `network_isolation_enforced`; существующие атаки без регрессий.
- [x] Runbook operations §19; Design §13.2; SPEC §7.
- **DoD:** worker не требует root/CAP_SYS_ADMIN; network-атаки блокируются
  в netns; 5+ тестов; runbook обновлён.

## S-98: Retention & Legal Hold (P1)

**Статус:** ✅ Завершён (2026-11-12)
**Цель:** PII в `email_outbox`, legal hold и удаление по запросу субъекта.

- [x] Retention `email_outbox`: body `[deleted]` через 30 дней, метаданные
      через 90 дней; архив gzip-JSONL без body; `EMAIL_OUTBOX_*` в env.
- [x] Legal hold: миграция `0036_s98_legal_hold`, API
      `POST/DELETE/GET /admin/legal-holds`; retention/DSAR пропускают
      субъекта, skip — в audit_logs.
- [x] DSAR `POST /admin/users/{id}/erase`: анонимизация users/profile,
      удаление outbox/tokens/sessions/links/review/pvp, erase
      bot/submission/game; 409 при активном hold; audit `user.erased`.
- [x] Метрики: `chessclass_legal_holds_active_total`,
      `chessclass_email_outbox_body_pending_scrub_total`,
      `chessclass_retention_last_success_timestamp_seconds`;
      алерты `ChessClassLegalHoldActive` (info), `ChessClassRetentionFailed`.
- [x] Тесты: body scrub, metadata delete, hold блокирует retention, DSAR
      PII, 409 при hold; миграция и runbook §20.
- **DoD:** policy применяется идемпотентно; hold/DSAR проверены тестами;
  метрики/алерты; отчёт `docs/sprint-reports/S-98-2026-11-12.md`.

## S-99: Release v0.9.0 (P0)

**Статус:** ✅ Завершён (2026-11-12)

- [x] Версия **0.9.0** во всех источниках: `backend/pyproject.toml`,
      `backend/app/__init__.py`, `backend/app/main.py`,
      `frontend/package.json`, `frontend/package-lock.json`,
      `IMAGE_TAG` prod/staging, `.env.*.example`; README/Design.
- [x] `docs/release-notes-v0.9.0.md`, CHANGELOG `[0.9.0]`, doc-lint:
      `CURRENT_VERSION=0.9.0`, `EXPECTED_VERSION=0.9.0`, прогресс `4/5`.
- [x] Финальные гейты: `ci.ps1`, `e2e.ps1 test`, `smtp-smoke.ps1`,
      `observability-selftest.ps1 -Stack`, staging acceptance, pip-audit,
      doc-lint; аудит алфавитов.
- [x] Тег `v0.9.0`, GHCR-образы `v0.9.0`, `docker pull`, отчёт S-99.
- **DoD:** все доступные спринты закрыты (S-95/S-96 могут остаться
  отложенными с явной пометкой), тег и образы опубликованы.

---

**Процесс:** ветки `feat/s-9x-*`; тесты только в Docker (`ci.ps1`,
`e2e.ps1`, `observability-selftest.ps1 -Stack`); doc-lint и аудит алфавитов
перед коммитом; отчёты — `docs/sprint-reports/S-9x-YYYY-MM-DD.md` по
`docs/RULES.md` §7.
