# SPEC.md — Контракты ChessClass

> **Назначение.** Живой справочник контрактных поверхностей: HTTP API v1,
> DTO, ошибки, события, промпт-таблицы и веса.
> Фундамент решений — `Design.md` (§12 API, §6/§7/§8 домены);
> здесь — только «что видно снаружи» и точные форматы.
> Не хватает факта → сначала добавить в Design, потом сюда.

## 1. Общие конвенции API v1

База всех роутов: `/api/v1`. Правила (обоснование — Design §12.1):

| Аспект | Контракт |
|---|---|
| Имена полей | camelCase (Pydantic `CamelModel` ↔ TS-интерфейсы) |
| Идентификаторы | целые числа как строки (JS-safe), timestamps — ISO 8601 UTC |
| Ошибки | RFC 7807, `application/problem+json`, поле `code` — машиночитаемый слаг |
| CORS | только origin фронтенда (dev: `localhost:3200`, `localhost:3201`) |
| Пагинация | `page` + `pageSize`; ответ `items[]` + `total` (с S-03) |
| Трассировка | каждый ответ несёт `x-request-id`; логи — JSON (Design §16.2) |

## 2. Сводная таблица эндпоинтов

Статусы: 🧱 — запланировано (спринт), ✅ — контракт закреплён и реализован.

| Домен | Route | Метод | Статус | Заметки |
|---|---|---|---|---|
| infra | `/healthz` (дублируется с корня `/`) | GET | ✅ S-01 | `HealthDto{status, db, redis}`; ping БД и Redis, сам никогда не 5xx |
| infra | `/readyz` (дублируется с корня `/`) | GET | ✅ S-03 | ревизия alembic vs head, версия приложения; `status: ready/not-ready` |
| auth | `POST /auth/register`, `/auth/verify`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me`, `POST /auth/password-reset`, `/auth/password-reset/confirm` | — | ✅ S-02 | Argon2id; JWT access 15м; refresh — opaque в БД, HttpOnly-cookie `cc_refresh` (path `/api/v1/auth`), ротация; login требует верифицированный email (Design §13.1) |
| profile | `GET /profile/me`, `PATCH /profile/me`, `GET /profile/students`, `GET /profile/{id}`, `PATCH /profile/{id}/level` | — | ✅ S-03 | RBAC: свой профиль — все; список/чужой — teacher/admin; смена уровня — admin (Design §12.2); пагинация `page`+`pageSize` |
| python | `/python/run` (песочница), `/python/lessons`, `/python/submissions` | — | 🧱 S-03…S-05 | контракт песочницы — Design §6, лимиты — ADR-002 |
| chess | `/chess/positions/analyze`, `/chess/games/{id}/summary`, экспорт PGN/CSV | — | 🧱 S-06…S-07 | engine-контракт — Design §7, ADR-003/004 |
| bots | `/bots` CRUD, `/bots/{id}/match/run` (SSE-прогресс), `/bots/{id}/reliability` | — | 🧱 S-08…S-09 | `choose_move(position)->str`, лестница Elo — Design §8, ADR-011/012 |
| skills | `/skills/snapshot`, `/skills/scores/{user}`, PDF родителям | — | 🧱 E-08…E-09 | EMA-скоры, fpdf2 + TTF — Design §9 |
| rag | `/rag/query`, инжест книжек | — | 🧱 S-10 | embeddings 768, pgvector — Design §10 |

## 3. Формат фиксации DTO

Каждый домен оформляет свои DTO в разделах ниже (или в специализированных
документах домена) по образцу:

```ts
// S-xx, домен <name>
interface SomeDto {
  id: string;        // целое число как строка
  createdAt: string; // ISO 8601 UTC
}
```

- Схема добавляется, когда контракт фиксируется в ревизии API.
- Добавление необязательного поля не ломает клиентов; ломающее изменение —
  только через решение в Design (мажор/минор номера фиксируются в §7).

### 3.1. auth (S-02, зафиксировано)

```ts
// POST /api/v1/auth/register → 201
interface RegisterOut { id: string; email: string; role: string; emailVerified: boolean }
// POST /api/v1/auth/login → 200 (+ Set-Cookie: cc_refresh, HttpOnly, SameSite=Lax)
interface AuthOut { accessToken: string; tokenType: "Bearer"; user: UserOut }
interface UserOut {
  id: string; email: string; role: string;
  emailVerified: boolean; isActive: boolean; createdAt: string;
}
// POST /api/v1/auth/refresh → 200 (ротация: Set-Cookie обновляется)
interface TokenOut { accessToken: string; tokenType: "Bearer" }
// /auth/verify, /auth/logout, /auth/password-reset(202), /auth/password-reset/confirm
interface MessageOut { ok: boolean }
```

Факты сверх каталога Design §11.2 (зафиксированы реализацией 0002):
`email_tokens`/`refresh_sessions` получили `created_at` (аудит); refresh-cookie
живёт с `path=/api/v1/auth`; повторное использование отозванного refresh
отзывает все сессии пользователя.

### 3.2. profile (S-03, зафиксировано)

```ts
// GET /api/v1/profile/me → 200
interface ProfileOut {
  id: string; email: string; role: string;
  displayName: string | null;
  level: "novice" | "intermediate" | "advanced" | null; // null — только легаси (до backfill 0003)
  billingTier: "free" | "pro" | null;
  emailVerified: boolean; isActive: boolean;
  prefs: Record<string, unknown>; createdAt: string;
}
// PATCH /profile/me { displayName?, prefs? } → ProfileOut (level меняет только admin)
// GET /profile/students?page&pageSize → { items: ProfileOut[], total, page, pageSize }
// PATCH /profile/{id}/level { level } → ProfileOut (только admin)
```

Профиль создаётся при регистрации (level `novice`, tier `free`) и всегда
существует у новых пользователей; миграция `0003` backfill-ом закрыла легаси.
Уровень попадает в JWT-клейм `level` при login/refresh. Данные `skills` /
`skill_links` пока без API (модели + seeds; таблицы — Design §11.2,
миграция `0003`) — API реестра появится вместе с дашбордом (E-08).

## 4. Канон ошибок

| `code` | HTTP | Когда |
|---|---|---|
| `validation_error` | 422 | Pydantic-валидация (поля — в `errors[]`) |
| `auth_unauthorized` | 401 | нет/кривой Bearer-токен (S-02) |
| `auth_invalid_token` | 401 | email-токен недействителен/истёк/использован (S-02) |
| `auth_invalid_credentials` | 401 | неверный email или пароль (S-02) |
| `auth_invalid_refresh` | 401 | нет/кривой/отозванный refresh-токен (S-02) |
| `auth_email_not_verified` | 403 | логин до подтверждения email (S-02) |
| `auth_inactive` | 403 | аккаунт деактивирован (S-02) |
| `auth_forbidden` | 403 | не хватает роли (S-02, `require_role`) |
| `auth_email_taken` | 409 | email уже зарегистрирован (S-02) |
| `rate_limited` | 429 | превышен rate-limit бакета (S-02) |
| `auth_locked_out` | 429 | 5 неудачных логинов/мин/IP → lockout 10 мин (S-02) |
| `quota_exceeded` | 429 | исчерпан LLM-бюджет дня (Design §5.4) |
| `sandbox_timeout` | 408 | таймаут кода/хода (ADR-002 и ботовый ADR) |
| `internal_error` | 500 | необработанное исключение |
| `http_404` … | 404/405… | универсальный маппинг Starlette |

Пример ответа `422`:

```json
{
  "type": "about:blank#validation_error",
  "title": "Validation error",
  "status": 422,
  "code": "validation_error",
  "errors": [{ "field": "level", "message": "not a valid enumeration member" }]
}
```

## 5. Живые события (SSE) — резерв

- `GET /api/v1/bots/{id}/match/events` — SSE-прогресс матча (полуход, доска).
- Воркер arq публикует в Redis pubsub; формат сообщения — JSON `{event, data}`.
- Контракт закрепляется в S-08; до этого не изобретаем поля.

## 6. LLM-шлюз: маршруты и модели (S-04)

Домены знают только маршрут `<domain>.<op>` и уровень (ADR-004); резолв тира —
`llm/routes.py`, слаги/цены — env + `llm/models_registry.py` (слаги сверяются
с провайдером на бутстрапе, R-01: несуществующий → warning + автопропуск).

### 6.1. Маршруты v0.1 → тир по уровню

| Маршрут | Назначение | novice/intermediate | advanced |
|---|---|---|---|
| `python_teacher.comment` | комментарий решения | L1 | L1 |
| `python_teacher.hint` | подсказка | L1 | **L2** |
| `python_teacher.explain_code` | разбор отправленного кода | L2 | L2 |
| `chess_lab.insight` | инсайт позиции | L2 | **L3** |
| `chess_lab.next_moves` | объяснение топ-3 ходов | L2 | L2 |
| `chess_lab.blunder` | объяснение плохого хода | L2 | L2 |
| `chess_lab.commentary` | комментарий/беседа | L1 | **L2** |
| `bot_lab.coach` | советы по боту (вне матчей) | L2 | L2 |
| `anticheat.judge_explain` | judge-сессия | **judge** | judge |
| `reports.parent_summary` | абзацы PDF-отчёта | L1 | L1 |

### 6.2. Модели и цены (₽/1M, Numeric(12,4))

| Тир | Слаг (default, env `LLM_MODEL_*`) | in | out | Роль |
|---|---|---|---|---|
| L1 | `minimax-m3.1` | 7 | 25 | комментарии/подсказки (массовые) |
| L2 | `deepseek-v4.1` | 26 | 100 | инсайты, разборы, бот-coach |
| L3 | `beam-1.0-501b` | 26 | 104 | advanced, сложные разборы |
| L3_alt | `claude-sonnet-5.5` | — | — | резерв/проверка качества (тариф RouterAI) |
| judge | `decider-flash-v1.2` | — | — | античит-judge (заполнить env `LLM_COST_JUDGE_*`) |

Параметры вызовов (temperature/max_tokens) — по маршрутам при переносе промптов
доменов (S-05+); карточки промптов живут в коде, здесь — идентификаторы.

### 6.3. API

- `GET /api/v1/admin/models` (admin) — реестр моделей: `{providerConfigured,
  currency, models[{tier, slug, display, role, configured, priceIn, priceOut}]}`;
  цены — строки Numeric (JSON JS-safe).
- `GET /api/v1/admin/finops/usage?days=7` (admin, 1–90) — агрегат по дням:
  `{currency, days[{day, users, tokensIn, tokensOut, costTotal}]}` (§6.4).

### 6.4. Экономика (S-05, зафиксировано)

**Fallback-цепочка** (Design §8.4): cloud RouterAI → local LM Studio
(флаг `LLM_LOCAL_FALLBACK`) → echo; в каждом шаге — 1 retry через
`LLM_RETRY_DELAY_S`. Причина переключения — `fallback_from`:
`cloud_not_configured` · слаг упавшей облачной модели · `lmstudio`-маркер ·
`quota_exhausted` · `quota_downgrade:{tier}`.

**llm_calls** (журнал, миграция 0004): `user_id` (nullable — system-вызовы),
`route`, `level`, `model_requested`, `model_used` (слаг / `lmstudio` / `echo`),
`fallback_from`, `tokens_in/out`, `cost_in/out` Numeric(12,4) (null, если цена
не задана), `latency_ms`, `status` (`ok | echo | error`), `task_kind`
(`sync | async`), `created_at`.

**Квоты и бюджеты** (Design §8.5): Redis-ключ `quota:{user}:{YYYY-MM-DD}`
(TTL 48 ч), бюджеты free 50 000 / pro 500 000 токенов/день
(`BUDGET_*_TOKENS_DAY`). Проверка перед вызовом; исчерпание → echo
(метка `quota_exhausted`); остаток меньше оценки входа и тир ≠ L1 →
downgrade до L1 (`quota_downgrade:{tier}`). `anticheat.judge_explain`
не расходует квоту (zero-квота); echo не инкрементирует счётчик и не пишет
`usage_daily`. День — UTC.

**usage_daily** (агрегат): PK `(user_id, day)`; `tokens_in/out`,
`cost_total`, `updated_at`; upsert-инкремент на каждый ok-вызов.

## 7. История ревизий контрактов

| Дата | Изменение | Спринт |
|---|---|---|
| 2026-10-31 | S-01: базовые конвенции v1, `/healthz` ✅ | S-01 |
| 2026-10-31 | S-02: auth-контракты ✅ — 8 эндпоинтов, DTO §3.1, 10 кодов ошибок | S-02 |
| 2026-10-31 | S-03: profile-контракты ✅ — 5 эндпоинтов, DTO §3.2, `/readyz`, пагинация включена | S-03 |
| 2026-10-31 | S-04: LLM-контракты ✅ — 10 маршрутов §6.1, реестр моделей §6.2, `GET /admin/models` | S-04 |
| 2026-10-31 | S-05: экономика ✅ — fallback-цепочка, llm_calls/usage_daily, квоты/бюджеты, FinOps API | S-05 |
