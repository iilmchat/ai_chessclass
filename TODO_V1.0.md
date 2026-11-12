# TODO_V1.0.md — План v1.0.0 «Production Ready»

**Статус:** ✅ Выпущен (v1.0.0 — Production Ready, 2026-11-12)
**Сводно:** 2 спринта · **Прогресс: 1/2**
**Цель:** выпустить финальный тег **v1.0.0** после успешной операционной
приёмки S-100; live LRS/TTS (S-95) — известное ограничение, отложенное до
v1.1.0 решением владельца.

**Условие выпуска v1.0.0 (выполнено):** финальная staging-приёмка
[`docs/runbooks/final-acceptance.md`](docs/runbooks/final-acceptance.md)
пройдена без critical (8/8 OK), GPU-станция отвечает через
`test-gpu-tunnel.ps1` (57.4 ток/с), а live LRS/TTS зафиксированы владельцем
как известное ограничение v1.0.0.

**Контекст:** цикл v0.9.0 закрыт (S-96…S-99 ✅), S-100 пройдена
(8/8 OK, GPU 57.4 ток/с), hotfix публичных auth-страниц влит в `main`;
план v0.9.0 — в [`docs/archive/TODO_V0.9.md`](docs/archive/TODO_V0.9.md).

## S-95: Live LRS/TTS (S-81) (P1)

**Статус:** ⏸️ Отложен до **v1.1.0** (решение владельца 2026-11-12)
**Причина:** нет боевых ключей LRS/ElevenLabs и доступа к провайдерам;
нельзя проверить OAuth2/refresh, квоты, rate-limit, стоимость TTS и
фактическую доставку писем. Контракты и fallback покрыты тестами
(MockTransport), staging-приёмка SMTP/SPF/DKIM/DMARC пройдена.

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
- **Решение владельца:** выпуск v1.0.0 с известным ограничением разрешён;
  интеграции переносятся в бэклог v1.1.0.

## S-101: Release v1.0.0 (P0)

**Статус:** ✅ Выполнен (2026-11-12) · **Тег:** `v1.0.0` ·
**Коммит:** см. отчёт [`S-101-2026-11-12.md`](docs/sprint-reports/S-101-2026-11-12.md)

- [x] Зафиксировать результат S-100: отчёт приёмки, отсутствие critical
      алертов, GPU live-факт; при незакрытом S-95 — письменное решение
      владельца о выпуске с известным ограничением.
      - [x] S-100: staging acceptance **8/8 OK**, GPU **57.4 ток/с**
            (`docs/runbooks/final-acceptance.md`).
      - [x] Hotfix email-routes: `/verify-email`, `/reset-password`, `/login`
            (отчёт `docs/sprint-reports/fix-email-routes-2026-11-12.md`).
      - [x] Решение владельца: v1.0.0 с ограничением, S-95 → v1.1.0.
- [x] Версия **1.0.0** во всех источниках: `backend/pyproject.toml`,
      `backend/app/__init__.py`, `backend/app/main.py`,
      `frontend/package.json`, `frontend/package-lock.json`,
      `IMAGE_TAG` prod/staging, `.env.*.example`; README/Design.
- [x] `docs/release-notes-v1.0.0.md`, CHANGELOG `[1.0.0]`, doc-lint:
      `CURRENT_VERSION=1.0.0`, `EXPECTED_VERSION=1.0.0`, `EXPECTED_PROGRESS=(1, 2)`.
- [x] README: бейдж **Production Ready**, итоговая таблица статуса,
      ссылки на release notes и отчёт S-101.
- [x] Финальные гейты: `ci.ps1`, `e2e.ps1 test`, `smtp-smoke.ps1`,
      `observability-selftest.ps1` (static), `pip-audit`, doc-lint, аудит
      алфавитов; `git diff --check`.
- [x] Тег `v1.0.0`, GHCR-образы `v1.0.0`, `docker pull`, отчёт S-101.
- **DoD:** приёмка S-100 зелёная, тег и образы опубликованы, README
  помечен Production Ready; известные ограничения перечислены явно.

---

**Процесс:** ветки `feat/s-1xx-*`; тесты только в Docker (`ci.ps1`,
`e2e.ps1`, `observability-selftest.ps1 -Stack`); doc-lint и аудит алфавитов
перед коммитом; отчёты — `docs/sprint-reports/S-1xx-YYYY-MM-DD.md` по
`docs/RULES.md` §7.
