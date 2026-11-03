# TODO_V0.4.md — Спринты этапа v0.4.0 (ChessClass)

**Статус:** план · **Дата:** 2026-11-03 · **Производная от:** `Design.md` §2.2,
релиза v0.3.0 (`docs/release-notes-v0.3.0.md`), отчётов S-46…S-57 и
независимой проверки релиза (backend 195 / frontend 5 / e2e 7/7, CI зелёный,
head `0028_rag_editor`).

> **Правила чтения.** v0.3.0 закрыт (12/12 спринтов, тег `v0.3.0`); здесь —
> следующий этап. Нумерация продолжается: S-58…S-69, этапы E-21…E-24.
> Каждый спринт — вертикальный срез: миграция → код → API/UI → тесты →
> документы. Отчёт — `docs/sprint-reports/S-XX-YYYY-MM-DD.md`.
> Статусы: ☐ не начат · 🔶 в работе · ✅ готов · 🚫 блокер.
> Оценка: **S** ≤ 3 дней · **M** ≤ 1 недели · **L** ≈ 2 недели.

**Сводно:** 12 спринтов / 4 этапа. **Прогресс: 1/12 закрыт (S-58 ✅);
S-59 🔶 — echo-базлайн снят, live ждёт ключей (S-60…S-69 ☐).**
Приоритет: **сначала staging и живая приёмка провайдеров, затем edge/CI,
продуктовая полнота UI и интеграции**. v0.4 — этап готовности к реальному
запуску, а не фичер-релиз: новых доменов нет.

**Вход (факт v0.3.0):** 195 backend-тестов, 5 frontend, Playwright 7/7;
28 миграций, head `0028_rag_editor`; CI — 3 job (`backend`/`frontend`/`e2e`).
**Зафиксированные ограничения v0.3.0:** живые LLM/voice не проверялись
(echo/hash), Telegram/LRS без токена/endpoint — graceful off, PvP и
RAG-редактор — API-only, CSP/axe/hash-lock/egress — остаточные риски,
матчи/LLM/турниры вне dev load-smoke (см. `docs/release-notes-v0.3.0.md`).

---

## E-21 · Staging, живые провайдеры и правда релиза (S-58…S-60)

### S-58 ✅ Staging-контур и env-контракт (2026-11-03)
- [x] `docker-compose.staging.yml` + `.env.staging.example`: prod-parity
      11 сервисов, порты 5440/6387/8032/3202/8080/8443 (ADR-014), отдельные
      volumes/сеть, `APP_ENV=staging`, `WEB_BASE_URL=https://localhost:8443`,
      edge TLS
- [x] `CORS_ORIGINS` в `backend/core/config.py` (comma/JSON, `NoDecode`)
      вместо хардкода в `backend/app/main.py`; warning при localhost-источниках
      в staging/prod; brand/stage UI через build-arg `APP_STAGE`
      (staging-образ `frontend:0.3.0-staging`)
- [x] staging: migrate/seed/backup→restore/smoke; env-дифф dev/staging/prod —
      `docs/runbooks/staging.md`; попутно `/readyz` version `0.1.0`→`0.3.0`
      и e2e redis `6385`→`6386` (KI-001)
- **DoD:** staging отвечает `/readyz` с head=`0028_rag_editor`; smoke-prod
  зелёный; CORS со staging-домена; backup/restore на staging проверен. ✅
- **Факт:** 10 контейнеров healthy (migrate — exit 0); seed `users=5`,
  `rag_documents=17`; `/readyz` `version=0.3.0`, `revision=head=0028`,
  `migrationsUpToDate=true`; smoke-prod 5/5 (healthz/readyz/SPA/edge
  healthz/HSTS); CORS preflight `Origin: https://localhost:8443` → 200 +
  `access-control-allow-origin`, evil-origin → 400 без заголовка; backup
  sha256 OK, restore `users=5 alembic=0028`; backend **197 passed**
  (195+2 CORS), ruff/mypy 0; frontend build + Vitest 5/5.
- **Отчёт:** `docs/sprint-reports/S-58-2026-11-03.md`.
- **Depends:** — · **Effort:** M · **Закрывает:** нет prod-подобного контура.

### S-59 🔶 Живая приёмка LLM и voice (часть 1 — 2026-11-03)
- [x] `backend/scripts/llm_smoke.py` v2: `--mode auto|echo|live`, `--out`
      JSON (schema `chessclass.llm_smoke/1`), `--compare` echo→live,
      `--with-voice`, `--with-pdf`, health провайдера, FinOps-сверка
      `llm_calls`/сегодня; +3 unit-теста (итого 200 backend-тестов)
- [x] echo-базлайн на staging: 4/4 `status=echo model=echo cost=0.0000`,
      `health=echo`, `voice=disabled` (graceful `voice_unavailable`),
      `pdf=ok` (`%PDF-`, 14 059 b); артефакт
      `docs/sprint-reports/S-59-echo-baseline-2026-11-03.json`; `--compare`
      и коды 0/2/3 проверены (live без провайдера → 3)
- [ ] реальные LLM/voice ключи на staging → live-прогон: 4/4 `status=ok`,
      health `ok`, 1 живой инсайт + 1 TTS, сверка `llm_calls`/цен/бюджетов,
      diff echo→live (ожидает ключей)
- **DoD:** логи 4+1+1, health live `status=ok`; деградации/лимиты записаны
  в runbook v0.4; echo-режим явно отличим от live — **частично** (echo-часть
  закрыта, live — после появления ключей).
- **Факт (часть 1):** staging echo: exit 0, 4 маршрута echo, cost 0;
  `voice=disabled`, `pdf=ok`; `--compare` echo→echo — 0/4 changed;
  `--mode live` без провайдера — exit 3; runbook `llm-gateway.md` §2.2 /
  `staging.md` §4 обновлены.
- **Отчёт:** `docs/sprint-reports/S-59-2026-11-03.md` (в работе, часть 1).
- **Depends:** S-58 · **Effort:** M · **Закрывает:** ядро продукта ни разу
  не работало с реальными ключами.

### S-60 ☐ Правда релиза, doc-lint и TODO_V0.4
- [ ] README/статус/версии/счётчики к факту; `Design.md` §2.2; runbook v0.3.0
- [ ] doc-lint в CI: версия (pyproject/package.json/`IMAGE_TAG`), head
      миграций, счётчики тестов, отсутствие заглушек `v0.2` в статусах
- [ ] этот `TODO_V0.4.md` — единственный активный план; `TODO_V0.1…V0.3` —
      архив (см. `docs/README.md`)
- **DoD:** расхождений «документ ↔ факт» нет; doc-lint зелёный на `main`.
- **Depends:** S-58 · **Effort:** S · **Закрывает:** дрейф документации
  v0.3.0 (README-статус, шапка Design, мутабельный `:prod`).

---

## E-22 · Edge, supply chain и ворота CI (S-61…S-63)

### S-61 ☐ CSP и egress allowlist
- [ ] CSP report-only на staging (аудит inline-стилей Vite) → enforce в
      `frontend/nginx.conf` и `deploy/nginx/edge.conf`
- [ ] egress allowlist для LLM/voice/Telegram/LRS: `ALLOWED_EGRESS_HOSTS` +
      проверка в httpx-клиентах
- **DoD:** `Content-Security-Policy` в staging/prod, 0 violations в e2e;
  egress-тест краснеет при обходе allowlist.
- **Depends:** S-58 · **Effort:** L · **Закрывает:** XSS-поверхность и
  неконтролируемый egress для детского prod (security-review §4).

### S-62 ☐ Hash-lock и воспроизводимая сборка
- [ ] `pip-compile --generate-hashes` → `backend/requirements.lock` +
      constraints; Dockerfile `--require-hashes`
- [ ] sha256 Stockfish-архива (`backend/Dockerfile:13-35`); `pip-audit` по
      финальному образу RC
- **DoD:** сборка только из lock; hash-mismatch ломает build; audit — no known.
- **Depends:** — · **Effort:** M · **Закрывает:** supply-chain риск A08.

### S-63 ☐ Ворота CI: security/a11y/load/docker/backup
- [ ] jobs: `pip-audit`, secrets scan (gitleaks), axe-core через Playwright,
      `docker build` api/web
- [ ] backup→restore smoke; scheduled load job (staging) с публикацией p95
- **DoD:** каждый gate падает на регрессии; CI ≤ 20 мин; отчёт gate-матрицы.
- **Depends:** S-61, S-62 · **Effort:** M · **Закрывает:** CI покрывает
  только ruff/mypy/pytest/build/e2e (security-review §5).

---

## E-23 · Продуктовая полнота заявленного v0.3 (S-64…S-66)

### S-64 ☐ RAG-редактор UI и gold-set eval
- [ ] экран `/admin/rag`: список/редактор/версии/publish/rollback/импорт/eval
      (`docs/SPEC.md` §3.25); доступ teacher/admin
- [ ] gold-set 3→20+ запросов, eval в `/ops`; OCR PDF — отложен
- **DoD:** учитель публикует материал без API и деплоя; eval ≥ baseline на
  20 запросах; версии/лицензии видны.
- **Depends:** S-58 · **Effort:** L · **Закрывает:** RAG-редактор API-only.

### S-65 ☐ PvP UI и workflow жалоб
- [ ] `/pvp`: комнаты, quick-match, SSE-доска, replay, лидерборд, зритель
- [ ] `PATCH /admin/complaints/{id}` (open→reviewed/rejected) + очередь
      жалоб у admin/teacher; сейчас статусы недостижимы API
- **DoD:** два браузера играют бот-матч; жалоба закрывается в UI; e2e PvP.
- **Depends:** S-58 · **Effort:** L · **Закрывает:** PvP API-only,
  `pvp_complaints` без ревью-эндпоинта.

### S-66 ☐ A11y/mobile и e2e новых экранов
- [ ] `aria-live`, контраст, 200%/320px, focus-trap модалок; axe на все
      маршруты
- [ ] e2e: PvP, RAG, review, ops, telegram-link — 7→12+ сценариев
- **DoD:** axe 0 critical/serious; a11y-чеклист `docs/a11y-audit.md` зелёный;
  e2e ≥ 12.
- **Depends:** S-64, S-65 · **Effort:** M · **Закрывает:** известные a11y-gaps
  и узкое e2e-покрытие.

---

## E-24 · Интеграции и релиз v0.4.0 (S-67…S-69)

### S-67 ☐ LRS OAuth2 и LMS-mapping
- [ ] OAuth2 client_credentials + token cache/refresh; Basic Auth — fallback
- [ ] mapping курсов/классов (`lms_courses`/`lms_class_map`), админ-редактор;
      повтор не дублирует statement
- **DoD:** statement доходит до тестового LRS через OAuth2; mapping виден
  в админке; журнал доставки без дублей.
- **Depends:** S-58, S-63 · **Effort:** L · **Закрывает:** LRS Basic-only,
  нет LMS-mapping (`docs/SPEC.md` §3.20).

### S-68 ☐ Telegram webhook, teacher-события, алерты
- [ ] webhook-endpoint + secret, обработка `/start`/отписки; fallback
      long-poll
- [ ] teacher-события (сдача/турнир/жалоба); алерты failed outbox/LRS в `/ops`
- **DoD:** живое уведомление и webhook-update на staging; failed outbox виден
  в алертах (сейчас алерты только по очередям/стоимости LLM).
- **Depends:** S-59, S-63 · **Effort:** M · **Закрывает:** тихие отказы
  интеграций, нет webhook.

### S-69 ☐ Staging load, prod-приёмка, релиз v0.4.0
- [ ] профили auth/read/SSE/матчи/LLM на staging (100/20), цели
      `docs/load-profile.md` §3
- [ ] prod: TLS/RS256/keys, backup/restore, e2e/smoke, demo-обход
      ученик→учитель→родитель→auditor→админ; тег `v0.4.0`, release-notes
- **DoD:** p95 в целях; приёмка с реальными ключами; CI зелёный; отчёты
  S-58…S-69; runbook v0.4.0.
- **Depends:** S-64…S-68 · **Effort:** M · **Закрывает:** load-smoke только
  health 30/5, prod-контур не принимался с живыми ключами.

---

## Зависимости и порядок

1. **S-58/S-59** — первыми: без staging и живой приёмки нельзя запускать
   продукт в школу.
2. **S-60** — сразу после S-58 (дешёво, убирает ложную картину у эксплуатации).
3. **S-61/S-62** — параллельно, независимые направления edge/supply chain.
4. **S-64/S-65** — после S-58; UI опирается на staging-конфиг и env-контракт.
5. **S-67/S-68** — после S-58/S-63; интеграции принимаются на staging.
6. **S-69** — в конце, только после зелёных S-58…S-68.

## Первая неделя (стартовый план)

- **Пн:** S-60 — фиксация факта (195/5/7, head 0028), doc-lint, этот TODO
  как активный план.
- **Вт:** S-58 — `docker-compose.staging.yml` + `.env.staging.example`,
  `CORS_ORIGINS`/`APP_ENV=staging`, brand из env.
- **Ср:** S-58 — staging up: migrate/seed/backup→restore/smoke, load baseline,
  env-дифф dev/staging/prod.
- **Чт:** S-59 — реальные ключи LLM/voice, `llm_smoke.py`, инсайт+TTS+PDF,
  сверка `llm_calls`.
- **Пт:** чеклист приёмки в runbook v0.4, отчёты S-58…S-60, go/no-go по E-22.

## Явно не входит в v0.4

- Новые домены и крупные фичи (PvP-движок в реальном времени, сезонные
  рейтинги, OCR PDF, полная LMS-платформа, маркетплейс этюдов/ботов).
- Нативные мобильные приложения, двусторонний голос, multi-tenancy/биллинг/SSO.
- k8s/autoscaling, HSM/KMS, внешние векторные БД, смена портов ADR-013.
- Маскировка echo-режима под live; `X-XSS-Protection` (устарел).

## Критерий релиза v0.4.0

- S-58…S-69 ✅; отчёты и CHANGELOG актуальны.
- Живые LLM/voice/Telegram/LRS приняты на staging; CSP enforce; egress-тест;
  hash-lock сборки.
- README/TODO/SPEC/runbook без дрейфа (doc-lint); axe 0 critical/serious;
  e2e ≥ 12; p95 в целях `docs/load-profile.md`.
- Backup/restore на prod; PvP и RAG-редактор доступны из UI; жалобы
  закрываются; demo-обход ученик→учитель→родитель→auditor→админ.
