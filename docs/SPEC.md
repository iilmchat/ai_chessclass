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
| auth | `/auth/register`, `/login`, `/refresh`, `/logout`, `/me` | — | 🧱 S-02 | Argon2id + PyJWT, refresh — HttpOnly cookie (Design §5.3) |
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

## 4. Канон ошибок

| `code` | HTTP | Когда |
|---|---|---|
| `validation_error` | 422 | Pydantic-валидация (поля — в `errors[]`) |
| `auth_invalid_credentials` | 401 | неверный логин/пароль/токен (S-02) |
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

## 6. Промпт-таблицы и веса (S-04+)

- Раздел открывается в S-04 (LLM-шлюз RouterAI): слаги моделей, их роли
  (L1/L2/L3/judge), античит «только флаги» (Design §6.5).
- Формат: таблица `операция × уровень → версия промпта`; сами карточки промптов
  живут в backend-коде, здесь — идентификатор и ссылка (один факт — один источник).

## 7. История ревизий контрактов

| Дата | Изменение | Спринт |
|---|---|---|
| 2026-10-31 | S-01: базовые конвенции v1, `/healthz` ✅ | S-01 |
