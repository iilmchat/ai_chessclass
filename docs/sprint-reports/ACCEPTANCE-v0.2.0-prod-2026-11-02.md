# Приёмка v0.2.0 на prod-контуре

**Дата:** 2026-11-02 · **Стенд:** локальный `docker-compose.prod.yml` (stand-in
prod; отдельные порты 8023/3211/8081/8444, self-signed TLS, временный env)
**Версия:** v0.2.0 (после приёмки — патч v0.2.1)

## 1. Что проверено

- [x] `docker compose --env-file ... -f docker-compose.prod.yml config -q`.
- [x] Сборка prod-образов backend/frontend; запуск db/redis/migrate/api/
      worker/4 match-worker/web/edge.
- [x] Миграции до head **`0021_tournaments`** (21).
- [x] Seed: 5 пользователей (admin/teacher/auditor/student1/student2),
      11 навыков, 5 skill_links, 16 заданий, 6 достижений, 17 RAG-документов
      (13 chess).
- [x] `smoke-prod.ps1`: healthz/readyz/web/edge HTTPS/HSTS — **OK**.
- [x] Live RouterAI `llm_smoke.py`: **4/4** маршрута `status=ok`
      (L1/L2/L3/judge).
- [x] Сценарий teacher: создать класс → добавить student1 → dashboard
      (11 навыков) → audit logs (2 записи) — **OK**.
- [x] Student: `/progress/me` (0/стрики), `/voice/status` (configured=false),
      `/studies` (0 published) — **OK**.
- [x] S-43: `POST /admin/studies/generate` → submit → approve → published;
      student attempt по solution — **correct=true**.
- [x] S-45: 8 ботов → bracket → **7 матчей**, status=done, 8 участников;
      tournament CSV 200.
- [x] LMS: `/admin/export/skills.csv` (200, 3022 байта),
      `/admin/export/xapi` (22 statements), tournament CSV (200).
- [x] Backup/restore: prod-дамп + `restore-test` → **users=5,
      alembic=0021_tournaments**, sha256 OK.

## 2. Найденный дефект и фикс

`docker-compose.prod.yml` задавал `LLM_EMBED_MODEL` как
`${LLM_EMBED_MODEL:-nomic-embed-text-v1.5}`. При пустом значении в `.env`
подставлялся несуществующий у провайдера слаг → seed делал лишние HTTP 400
и падал в hash-фолбэк.

Исправлено на `${LLM_EMBED_MODEL:-}`; после пересоздания API:
`settings.llm_embed_model == ''`, hash-режим без сетевых вызовов.
Патч-релиз: **v0.2.1**.

## 3. Ограничения приёмки

- Стенд локальный (stand-in prod), не внешний сервер; DNS/Let's Encrypt не
  проверялись — self-signed TLS.
- `VOICE_API_KEY` пуст: озвучка проверена только как graceful fallback
  (`configured=false`, `/voice/speak` → 503).
- Временный prod-стек, volumes, `.env.prod.acceptance` и сертификаты удалены
  после проверки; dev-стек не затронут.

## 4. Итог

**Приёмка v0.2.0 пройдена.** После фикса embed-модели выпущен патч v0.2.1.
Следующий этап — `TODO_V0.3.md` (S-46…S-57).
