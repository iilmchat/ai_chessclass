# Runbook — release v0.4.0 (S-69)

**Дата:** 2026-11-04 · ответственный: релиз-инженер · шаблон RULES §7.

## 1. Что релизим

Версия **0.4.0**: staging-контур, egress/CSP, hash-lock сборка, CI-ворота
(gitleaks/pip-audit/axe/backup-smoke/load-cron), RAG-редактор + gold-set
eval, PvP-жалобы, a11y-гейт (axe на 20 маршрутах, e2e 14), LRS OAuth2 +
LMS-mapping (0030), Telegram webhook + teacher-события + алерты.

## 2. Release gates (локальный факт, 2026-11-04)

- Alembic head **0030_s67_lms_oauth** (30); backup_smoke EXPECTED_HEAD — 0030.
- pytest **232 passed + 3 skipped = 235 collected**; ruff 0; mypy 253 files.
- frontend: tsc 0, vitest **5 passed**, build ok.
- doc-lint **6/6** (`scripts/doc_lint.py --tests-count auto`); версии 0.4.0
  во всех источниках (A-check).
- Аудит смешанных алфавитов — CLEAN (PowerShell-регекс RULES §7).
- Целевой e2e (S-66/67 UI): **6 passed**; **полный набор 14 passed (47 c)**
  на свежем стеке v0.4.0 (после стабилизации RAG-теста: reload + expect).
- Живые прогон: release-notes `docs/release-notes-v0.4.0.md`.

## 3. Staging-контур

- Подъём: `docker-compose.staging.yml` + `.env.staging` (шаблон
  `.env.staging.example`); порты pg 5440 / redis 6387 / api 8032 / web 3202
  / edge 8080+8443 (ADR-014); `APP_ENV=staging`.
- Миграции: `run migrate` → head **0030**; seed — одноразово.
- Smoke: `healthz`, `readyz` (head/версия), `scripts/llm_smoke.py --mode echo`,
  CSP report-only (`CSP_MODE`), backup→restore `scripts/backup.ps1` +
  `scripts/restore-test.ps1`.

## 4. Основной приёмочный прогон (орошение)

1. Полный e2e на свежем стенде: `scripts/e2e.ps1 test` — **14 get pass**
   (journey 7 + axe 2 + PvP 1 + screens 4); CI e2e job зеленый.
2. Load smoke против api: `python scripts/load_smoke.py --base-url
   http://127.0.0.1:<api> --requests 100 --concurrency 20 --p95-ms 150`
   → JSON (errors=0, p95 в цели); тот же скрипт в `.github/workflows/load.yml`
   (cron пн 04:00 UTC) — p95 в Step Summary.
3. Backup→restore smoke: `scripts/ci/backup_smoke.sh` (CI) — users/alembic/
   sha256; EXPECTED_HEAD сверяется c фактом (править при новой миграции!).

## 5. Фиксированные ограничения приёмки (не блокеры кода)

- **Staging load 100/20 и prod-приёмка с живыми ключами** (LLM RouterAI,
  live Telegram-бот, live LRS/OAuth IdP) недоступны из этой рабочей
  машины — стенд staging не развёрнут локально; факт фиксируется в
  этом runbook как отдельное действие эксплуатации.
  - Живые ключи: `LLM_API_KEY` (RouterAI 4/4 в S-59), `TELEGRAM_BOT_TOKEN`
    + `TELEGRAM_WEBHOOK_SECRET`, `LRS_*` + `LRS_OAUTH_*` — приёмка по
    `docs/runbooks/staging.md` §8 и `llm-gateway.md` §5.
- Полный e2e прогон повторно на CI в release-push — автоматический (CI).

## 6. Rollback

- Тег `v0.4.0`; откат — `IMAGE_TAG=0.3.0` в prod/staging compose
  (`docker compose ... up -d`) и `alembic downgrade 0029_pvp_complaint_review`
  (миграция 0030 — только create/drop таблиц, данных не переносит).

## 7. Команда релиза (гит)

```bash
git checkout main
git log --oneline -1            # S-69-коммит
git tag -a v0.4.0 -m "ChessClass v0.4.0 -- staging, egress/CSP, hash-lock, CI gates, RAG editor, PvP complaints, a11y gate, LRS OAuth2+mapping, Telegram webhook" # noqa — одна строка
git push origin v0.4.0
gh release create v0.4.0 --title "ChessClass v0.4.0" --notes-file docs/release-notes-v0.4.0.md
```

**Факт (2026-11-04):** тег `v0.4.0` (коммит `3bbf8c1`) + GitHub Release
`https://github.com/iilmchat/ai_chessclass/releases/tag/v0.4.0`;
CI релиз-коммита — run **41753445116, success** (перед релизом
готовил readyz-тест: версия из `app.__version__`, не хардкод).

CI после push — зелёный (счётчики/док-линт альвины); следить:
`gh run watch <run-id> --exit-status`.
