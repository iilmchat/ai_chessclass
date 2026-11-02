# TODO_V0.3.md — Спринты этапа v0.3.0 (ChessClass)

**Статус:** план · **Дата:** 2026-11-02 · **Производная от:** `Design.md` §2.2,
приёмки v0.2.0 и отчётов S-30…S-45.

> **Правила чтения.** v0.2.0 закрыт (16/16 спринтов, тег `v0.2.0`); здесь —
> следующий этап. Нумерация продолжается: S-46…S-57, этапы E-17…E-20.
> Каждый спринт — вертикальный срез: миграция → код → API/UI → тесты →
> документы. Отчёт — `docs/sprint-reports/S-XX-YYYY-MM-DD.md`.
> Статусы: ☐ не начат · 🔶 в работе · ✅ готов · 🚫 блокер.

**Сводно:** 12 спринтов / 4 этапа. **Прогресс: 8/12 (S-46…S-53 ✅).**
Приоритет: **сначала надёжность и безопасность, затем интеграции, контент
и релиз**. Все спринты — после стабилизации v0.2.x.

---

## E-17 · Надёжность, безопасность и эксплуатация (S-46…S-48)

### S-46 ✅ Retention, наблюдаемость и стоимость
- [x] retention/архив для `audit_logs`, `voice_audio`, `chess_studies`,
      `llm_calls` (политика, cron/arq, отчёт)
- [x] метрики Prometheus/health: очереди, LLM/voice расход, ошибки, p95;
      алерты по бюджету/диску/сертификату
- [x] дашборд «стоимость на ученика» (LLM + voice), экспорт для администратора
- **DoD:** журналы/кэш не растут бесконечно; есть дашборд и алерты; retention
  не ломает restore (S-38).
- **Факт:** миграция `0022_observability` (`voice_usage`); `domains/retention`
  (gzip-архив + удаление, dry-run), worker cron 04:10 UTC; `/metrics`,
  `/admin/observability/{summary,alerts,costs,costs.csv,retention/*}`;
  UI `/ops`; retention тест + observability тест; backend 176, frontend 5.
- **Отчёт:** `docs/sprint-reports/S-46-2026-11-02.md`.

### S-47 ✅ Auth-hardening и приватность
- [x] RS256/JWKS (ротация ключей), совместимость HS256 на переходный период
- [x] аудит логинов/смены ролей; ограничение доступа auditor по scope
- [x] валидация `age_group`/PII, политика удаления/анонимизации ученика
- [x] security-тесты: token confusion, refresh reuse, role escalation
- **DoD:** RS256 включается конфигом; старые токены не ломаются; PII-политика
  зафиксирована в SPEC/runbook.
- **Факт:** `jwt_algorithm=RS256` + private/public keys/paths, `kid`,
  legacy HS256; JWKS `/api/v1/auth/jwks` + `/.well-known/jwks.json`;
  `auth.login.success/failed`, `auth.role.change`, `auth.auditor_scope.change`,
  `auth.user.anonymize` в audit; admin role/scope/anonymize endpoints;
  scope auditor (flags/audit/reports/observability); `gen-jwt-keys.ps1`;
  backend 179, frontend 5.
- **Отчёт:** `docs/sprint-reports/S-47-2026-11-02.md`.

### S-48 ✅ Турниры v2: async, replay и античит
- [x] arq-job турнира + SSE-прогресс; round-robin без блокировки API
- [x] запись ходов турнира (`tournament_moves`), реплей, seed/ничьи
- [x] античит: семплирование SF, флаги `engine_likeliness` для турнирных ботов
- [x] лимиты/бюджет турнира, отмена и восстановление после рестарта
- **DoD:** турнир 8/16 ботов идёт асинхронно; реплей доступен; флаги
  появляются у teacher; рестарт не теряет турнир.
- **Факт:** миграция `0023_tournament_v2` (`progress/total/job/cancel/error`,
  `tournament_moves`); arq `run_tournament_job` + recovery-cron
  `resume_tournaments`; SSE `/tournaments/{id}/events`; replay endpoint;
  cancel; SF-семплы и `engine_likeliness`; UI polling/replay/cancel;
  backend 181, frontend 5, build OK.
- **Отчёт:** `docs/sprint-reports/S-48-2026-11-02.md`.

---

## E-18 · Интеграции и вовлечение (S-49…S-51)

### S-49 ✅ LMS: xAPI LRS-адаптер и расписание экспорта
- [x] коннектор LRS (endpoint/key), retry/идемпотентность statements
- [x] scheduled export (cron/arq), журнал доставки, статус в админке
- [x] настройка маппинга навыков/классов на LMS-курсы
- **DoD:** statements доходят до тестового LRS; повтор не дублирует; сбой
  виден администратору.
- **Факт:** миграция `0024_lms` (`lrs_deliveries`, unique statement_id);
  xAPI builder + идемпотентная очередь, retry/backoff; worker `lms_sync`
  (minute=15); `/admin/lms/{status,sync,deliveries,deliveries.csv}`;
  mapping — стандартные activity id (skills/bot-elo); backend 183, frontend 5.
- **Отчёт:** `docs/sprint-reports/S-49-2026-11-02.md`.

### S-50 ✅ Telegram-бот: уведомления ученику/учителю
- [x] привязка Telegram к профилю (код/ deep link), consent
- [x] уведомления: бейдж, стрик, проверка учителем, PDF готов
- [x] rate-limit/отписка; без токена — graceful off
- **DoD:** уведомление приходит при привязке; отписка работает; секреты не
  логируются.
- **Факт:** миграция `0025_telegram` (`telegram_links`, `telegram_outbox`);
  direct link + code/deep-link confirm, consent; outbox retry/backoff;
  worker `telegram_deliver` (minute=2); `/telegram/{status,link,link-code,confirm}`,
  DELETE link; уведомления при бейдже и готовом PDF; UI в профиле;
  без `TELEGRAM_BOT_TOKEN` — disabled, тесты на fake sender; backend 186.
- **Отчёт:** `docs/sprint-reports/S-50-2026-11-03.md`.

### S-51 ✅ PvP-матчи ботов
- [x] комнаты/приглашения, матчмейкинг по Elo, лимиты
- [x] бот vs бот в реальном времени/SSE, реплей, зрители
- [x] античит и жалобы; рейтинг PvP отдельно от лестницы
- **DoD:** два ученика играют бот-матч; результат/реплей сохраняются;
  превышение лимитов — 429.
- **Факт:** миграция `0026_pvp` (`pvp_rooms`, `pvp_ratings`,
  `pvp_complaints`); комнаты/код/join/quick-match ±300 Elo; start создаёт
  bracket-турнир из 2 ботов и arq-job; SSE `/pvp/rooms/{id}/events`,
  replay, leaderboard; отдельный PvP-Elo (K=24); жалобы/admin;
  tournament-job финализирует комнату; backend 188, frontend 5/build.
- **Отчёт:** `docs/sprint-reports/S-51-2026-11-03.md`.

---

## E-19 · Контент и обучение (S-52…S-54)

### S-52 ✅ Spaced-repetition тренажёр
- [x] карточки/интервалы (SM-2), очередь повторений, напоминания
- [x] интеграция с ошибками Python/шахмат; статистика усвоения
- [x] UI «Повторение» + API; ограничение дневной нагрузки
- **DoD:** карточка возвращается по интервалу; правильный/неверный ответ
  меняет следующий срок; данные не теряются при рестарте.
- **Факт:** миграция `0027_review` (`review_cards`, `review_events`);
  SM-2 (again/hard/good/easy), дневной лимит 20; API `/review/{queue,cards,
  cards/{id}/answer,stats}`; автокарочки из failed Python и chess-blunder;
  UI `/review`; данные в PostgreSQL; backend 190, frontend build OK.
- **Отчёт:** `docs/sprint-reports/S-52-2026-11-03.md`.

### S-53 ✅ Генератор этюдов v2
- [x] random-playout/этюдная база + дедупликация по FEN
- [x] многоходовый solver (линия/альтернативы), сложность по SF
- [x] батч-генерация с лимитом, авто-ревью, метрики брака
- **DoD:** 20 этюдов без дублей; многоходовые проверяются; брак < 20 %.
- **Факт:** random-playout + curated-база; batch 1–20 с `exclude_fens`
  (uniqueFens/skipped/defectRate); autoReview (FEN/легальность линии) в
  generator_meta; `attempt-line` проверяет PV/префикс; difficulty по SF
  score; `/admin/studies/generate-batch|generator/metrics`; backend 192.
- **Отчёт:** `docs/sprint-reports/S-53-2026-11-03.md`.

### S-54 ☐ RAG/контент-редактура
- [ ] админ-редактор документов/версий, публикация и откат
- [ ] полнотекстовый + векторный гибрид, eval ≥ baseline
- [ ] источники/лицензии, импорт PDF/Markdown
- **DoD:** учитель добавляет материал без деплоя; eval не деградирует;
  версии/лицензии видны.

---

## E-20 · Качество и релиз v0.3.0 (S-55…S-57)

### S-55 ☐ Нагрузка, доступность и безопасность
- [ ] нагрузочный профиль (матчи/турниры/LLM), p95 и лимиты
- [ ] accessibility (клавиатура/контраст), мобильный UX
- [ ] security-ревью: OWASP-чеклист, зависимости, secrets scan
- **DoD:** целевые p95 соблюдены; a11y-чеклист; нет critical/high
  уязвимостей.

### S-56 ☐ Release candidate v0.3.0
- [ ] все миграции/seed/backup/restore на prod-контуре
- [ ] e2e + smoke + live LLM/voice (или явный echo/fallback)
- [ ] документация/CHANGELOG/README/SPEC/runbook актуальны
- **DoD:** RC проходит приёмку; известные ограничения зафиксированы.

### S-57 ☐ Релиз v0.3.0
- [ ] тег `v0.3.0`, GitHub Release, отчёт
- [ ] демо-обход: ученик → учитель → родитель → auditor → админ
- [ ] план следующего этапа (v0.4/backlog)
- **DoD:** тег и release созданы; CI зелёный; demo-обход без блокеров.

---

## Зависимости и порядок

1. **S-46/S-47** — первыми: без retention/безопасности нельзя масштабировать.
2. **S-48** — после S-46/S-47; async-турниры используют arq/SSE.
3. **S-49/S-50** — параллельно, независимые интеграции.
4. **S-51** — после S-48 (общий replay/античит).
5. **S-52…S-54** — после стабилизации API; можно параллельно.
6. **S-55…S-57** — в конце, только после зелёных S-46…S-54.

## Явно не входит в v0.3

- Полноценная LMS-платформа (только коннектор/экспорт).
- Голосовая двусторонняя связь (только TTS v0.2).
- Мобильные нативные приложения.
- Публичный маркетплейс этюдов/ботов.

## Критерий релиза v0.3.0

- 12/12 спринтов ✅, отчёты и CHANGELOG актуальны.
- backend + frontend + Playwright зелёные; ruff/mypy/tsc 0.
- миграции head соответствует SPEC; backup/restore и HTTPS проверены.
- live LLM/voice или явный fallback; retention/алерты работают.
- demo-обход ученик → учитель → родитель → auditor → админ.
