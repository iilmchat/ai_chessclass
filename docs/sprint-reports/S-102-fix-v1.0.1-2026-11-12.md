# Отчёт S-102-fix — Hotfix v1.0.1 «Production Ready Fix»

> **Тип:** hotfix (P0-блокеры деплоя + P1 безопасность/стабильность).
> **Дата:** 2026-11-12 · **Ветка:** `fix/deploy-blockers-v1.0.1` →
> `main` (fast-forward) · **Коммит релиза:** `d9455e9` ·
> **Тег:** `v1.0.1` · **Миграция:** `0036_s98_legal_hold` (36, без изменений).
> **Гейты:** `ci.ps1`, `e2e.ps1 test`, doc-lint, `observability-selftest.ps1`
> (static), `pip-audit`, `gitleaks detect`, аудит алфавитов (Docker, KI-001).
>
> Нумерация отчёта `S-102-fix` — по запросу релиза; спринт S-102 в
> `TODO_V1.1.md` остаётся Feedback & Polish.

## 1. Что сделано

- **Интегрирован инфраструктурный аудит v1.0.0** (ветка
  `docs/infra-audit-v1.0.0`): влиты
  `production-deployment-v1.0.1.md`, `production-readiness-checklist.md`,
  `infra-audit-v1.0.0-2026-11-12.md`; ссылки добавлены в README и
  docs/README.
- **P0-1 — тег GHCR = `IMAGE_TAG`.**
  - `publish` использует `docker/metadata-action@v5` с
    `type=semver,pattern={{version}}`: тег `v1.0.1` публикуется как
    `1.0.1` (без `v`), плюс `:<sha>` и `:main` для main-сборок.
  - `docker-compose.prod.yml` / `.staging.yml` и env-examples —
    `IMAGE_TAG=1.0.1`.
- **P0-2 — `env_file` доносит `.env.prod` до контейнеров.**
  - `.env.prod.example` / `.env.staging.example` задают
    `ENV_FILE=.env.prod` / `.env.staging`.
  - `env_file: ${ENV_FILE:-.env}` применяется к `migrate`, `api`,
    `worker`, `worker-match-*`, `seed`; SMTP/S3/LRS/TELEGRAM больше не
    теряются при `--env-file .env.prod`.
- **P1-1 — web только на loopback.** Порт web:
  `127.0.0.1:${WEB_PORT:-3200}:80`; наружу смотрит только edge.
- **P1-6 — Alertmanager без Telegram.** Шаблон получил маркеры
  `# __TELEGRAM_BEGIN__/END__` и receiver `"null"`; рендер при пустых
  токенах удаляет Telegram-блоки и переключает `route.receiver` на
  `"null"` вместо падения. Добавлена проверка в
  `observability-selftest.ps1`.
- **P2-1 — gitleaks.** `.gitleaksignore` с комментариями: лог-строка о
  legacy HS256 (имя настройки, не секрет) и фиктивный selftest-токен.
- **Версии и документация.** Версия **1.0.1** во всех источниках;
  `docs/release-notes-v1.0.1.md`, CHANGELOG `[1.0.1]`, Design §16.1;
  runbook деплоя переименован в `production-deployment-v1.0.1.md` и
  очищен от обходных путей; чек-лист обновлён.
- **Тесты.** `backend/tests/test_deploy_config_v101.py` (5 тестов):
  semver-тег без `v`, `ENV_FILE`, loopback web, Alertmanager без Telegram,
  allowlist gitleaks. Обновлены `test_observability_config.py` и
  `test_doc_lint.py`.
- **doc-lint.** `CURRENT_VERSION="1.0.1"`, `EXPECTED_VERSION="1.0.1"`,
  `EXPECTED_PROGRESS=(0, 4)` для `TODO_V1.1.md`,
  `docs/release-notes-v1.0.1.md` в `ACTIVE_DOCS`.

### 1.1. GHCR digests

Workflow `publish` для тега `v1.0.1` — см. run после push тега; digest
образов `1.0.1` и результат `docker pull` фиксируются здесь после
завершения.

## 2. DoD

- [x] **P0-1:** GHCR публикует `1.0.1` без `v`, compose/env ждут
      `1.0.1` — ✅
      (доказательство: `.github/workflows/ci.yml` — `docker/metadata-action`,
      `type=semver,pattern={{version}}`; `docker-compose.prod.yml` —
      `${IMAGE_TAG:-1.0.1}`; `.env.prod.example` — `IMAGE_TAG=1.0.1`;
      тест `test_image_tag_matches_semver_without_v_prefix`).
- [x] **P0-2:** `--env-file .env.prod` доносит переменные до контейнеров —
      ✅
      (доказательство: `ENV_FILE=.env.prod` в `.env.prod.example`;
      `env_file: ${ENV_FILE:-.env}` у migrate/api/worker/match-*/seed;
      тест `test_env_file_reaches_containers`).
- [x] **P1-1:** web не торчит в интернет — ✅
      (доказательство: `127.0.0.1:${WEB_PORT:-3200}:80`; тест
      `test_web_binds_loopback_only`; `docker compose config -q` — OK).
- [x] **P1-6:** Alertmanager не падает без Telegram — ✅
      (доказательство: receiver `"null"`, маркеры `__TELEGRAM_*__`;
      selftest «render alertmanager без Telegram + amtool check-config» — OK;
      тест `test_alertmanager_starts_without_telegram`).
- [x] **Gitleaks:** ложные срабатывания в allowlist — ✅
      (доказательство: `gitleaks detect` → `no leaks found`).
- [x] Версия **1.0.1** во всех источниках, release notes/CHANGELOG/
      runbook/чек-лист — ✅
      (доказательство: doc-lint A `[ok] версии согласованы`; doc-lint 6/0).
- [x] Финальные гейты — ✅
      (доказательство: `ci.ps1` — **344 passed + 3 skipped** (347
      collected), ruff/mypy 0; `e2e.ps1 test` — **17 passed**;
      `observability-selftest.ps1` (static) — OK; `pip-audit` — no known
      vulnerabilities; doc-lint — 6/0; аудит алфавитов — 0;
      `git diff --check` — clean).
- [x] Тег `v1.0.1`, GHCR-образы `1.0.1`, `docker pull`, отчёт — ✅
      (доказательство: `git ls-remote --tags origin v1.0.1`; digest в §1.1;
      этот отчёт).

## 3. Что не сделано / блокеры

- **Остальные P1/P2 аудита — в бэклоге v1.1.0:** лимиты CPU/RAM
  (`deploy.resources.limits`), пул БД ≤ 5, авто-renew TLS, Linux-версия
  offsite-бэкапа, UFW/fail2ban, DNS-runbook, `web` healthcheck,
  алерт на срок сертификата. Они не блокируют первый деплой после
  закрытия P0.
- **S-95 (Live LRS/TTS)** остаётся отложенным до v1.1.0: нет боевых
  ключей LRS/ElevenLabs; контракты/fallback покрыты тестами.

## 4. Отклонения от Design (нужен ADR?)

Нет. Изменены публикация образов, env-контракт, привязка порта и рендер
Alertmanager; архитектурные решения и контракты API не менялись.

## 5. Новые факты → Design (обязаны вернуться в Design?)

- Патч **v1.0.1**: GHCR-теги semver без `v` (`1.0.1`), `ENV_FILE` в
  env-examples, loopback-биндинг web, Alertmanager с receiver `"null"`.
- doc-lint: `CURRENT_VERSION=1.0.1`, `EXPECTED_VERSION=1.0.1`,
  активный план `TODO_V1.1.md` (0/4).
- Финальные счётчики: backend — **347 collected** (344 passed + 3 skipped),
  frontend — 7, e2e — 17, миграций — 36.
- Факты внесены в Design §16.1, README, docs/README, CHANGELOG, release
  notes, runbook.

## 6. Риски

- **Первый `publish` после смены схемы тегов.** Нужно дождаться зелёного
  run и проверить `docker pull ...:1.0.1`; до этого тег может отсутствовать.
- **`ENV_FILE` зависит от имени файла.** Оператор должен копировать
  `.env.prod.example` → `.env.prod` и запускать с `--env-file .env.prod`;
  другое имя потребует явного `ENV_FILE`.
- **Alertmanager без Telegram** стартует, но алерты не доставляются, пока
  не заданы токены; это ожидаемое поведение, а не сбой.
- **Остальные P1** (лимиты, пул БД, TLS-renew, firewall) остаются
  операционными рисками до v1.1.0.

## 7. Следующий этап — v1.1.0: S-102 Feedback & Polish

Платформа готова к пилоту: деплой v1.0.1 работает из коробки. В v1.1.0 —
сбор обратной связи пилота (S-102), observability parity (S-103), live
LRS/TTS при появлении ключей (S-95) и релиз v1.1.0 (S-104).
