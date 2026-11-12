# TODO_V1.0.md — План v1.0.0 «Production Ready»

**Статус:** 🔶 Черновик (активный план; v1.0.0 — после staging acceptance)
**Сводно:** 2 спринта · **Прогресс: 0/2**
**Цель:** закрыть последний отложенный контур (live LRS/TTS) и выпустить
финальный тег **v1.0.0** после успешной операционной приёмки S-100.

**Условие выпуска v1.0.0:** финальная staging-приёмка
[`docs/runbooks/final-acceptance.md`](docs/runbooks/final-acceptance.md)
пройдена без critical, GPU-станция отвечает через `test-gpu-tunnel.ps1`,
а live LRS/TTS либо подтверждены, либо владелец проекта явно зафиксировал
их как известное ограничение v1.0.0.

**Контекст:** цикл v0.9.0 закрыт (S-96…S-99 ✅), S-100 — операция
(приёмка + GPU), план v0.9.0 — в
[`docs/archive/TODO_V0.9.md`](docs/archive/TODO_V0.9.md).

## S-95: Live LRS/TTS (S-81) (P1)

**Статус:** ⏸️ Отложен (нет боевых ключей LRS/ElevenLabs)
**Причина:** без доступа к провайдерам нельзя проверить OAuth2/refresh,
квоты, rate-limit, стоимость TTS и фактическую доставку писем.

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

## S-101: Release v1.0.0 (P0)

**Статус:** ☐ Запланирован (старт — только после S-100 и S-95/решения
владельца)

- [ ] Зафиксировать результат S-100: отчёт приёмки, отсутствие critical
      алертов, GPU live-факт; при незакрытом S-95 — письменное решение
      владельца о выпуске с известным ограничением.
- [ ] Версия **1.0.0** во всех источниках: `backend/pyproject.toml`,
      `backend/app/__init__.py`, `backend/app/main.py`,
      `frontend/package.json`, `frontend/package-lock.json`,
      `IMAGE_TAG` prod/staging, `.env.*.example`; README/Design.
- [ ] `docs/release-notes-v1.0.0.md`, CHANGELOG `[1.0.0]`, doc-lint:
      `CURRENT_VERSION=1.0.0`, `EXPECTED_VERSION=1.0.0`.
- [ ] README: бейдж **Production Ready**, итоговая таблица статуса,
      ссылки на release notes и отчёт S-101.
- [ ] Финальные гейты: `ci.ps1`, `e2e.ps1 test`, `smtp-smoke.ps1`,
      `observability-selftest.ps1 -Stack`, `pip-audit`, doc-lint, аудит
      алфавитов; `git diff --check`.
- [ ] Тег `v1.0.0`, GHCR-образы `v1.0.0`, `docker pull`, отчёт S-101.
- **DoD:** приёмка S-100 зелёная, тег и образы опубликованы, README
  помечен Production Ready; известные ограничения перечислены явно.

---

**Процесс:** ветки `feat/s-1xx-*`; тесты только в Docker (`ci.ps1`,
`e2e.ps1`, `observability-selftest.ps1 -Stack`); doc-lint и аудит алфавитов
перед коммитом; отчёты — `docs/sprint-reports/S-1xx-YYYY-MM-DD.md` по
`docs/RULES.md` §7.
