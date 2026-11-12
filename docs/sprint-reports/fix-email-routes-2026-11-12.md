# Отчёт Hotfix — публичные страницы verify-email и reset-password

> **Тип:** hotfix (P0-блокер v1.0.0). Дата: 2026-11-12.
> Ветка: `fix/email-routes-v1.0`. План: [`TODO_V1.0.md`](../../TODO_V1.0.md).

## 1. Что сделано

- Добавлена публичная страница **`/verify-email`**
  (`frontend/src/pages/VerifyEmailPage.tsx`): токен из query, вызов
  `POST /api/v1/auth/verify`, состояния `loading`/`success`/`error`,
  кнопка «Перейти к входу».
- Добавлена публичная страница **`/reset-password`**
  (`frontend/src/pages/ResetPasswordPage.tsx`): токен из query, два поля,
  проверка минимум 8 символов и совпадения, вызов
  `POST /api/v1/auth/password-reset/confirm` с `newPassword`, состояния
  `loading`/`success`/`error`.
- Добавлена публичная **`/login`** (`frontend/src/pages/LoginPage.tsx`),
  чтобы кнопки со страниц не вели на пустой маршрут.
- `frontend/src/shared/api.ts`: `verifyEmail(token)` и
  `resetPassword(token, newPassword)`.
- `frontend/src/app/App.tsx`: маршруты добавлены в публичную секцию
  `Routes` (без `ProtectedRoute`).
- Тесты: Vitest `VerifyEmailPage.test.tsx` (успех + ошибка, мок `fetch`);
  Playwright `screens.spec.ts` — `/verify-email?token=fake` показывает
  «Токен недействителен».
- Документация: черновик `docs/release-notes-v1.0.0.md`, CHANGELOG
  `[Unreleased]`, `TODO_V1.0.md` S-101 (пункт не закрыт ✅).
- CI-фикс: `test_edge_auth_s90.py` приведён к hardening `7bbdf90`
  (edge не принимает клиентский `X-Forwarded-For`).

## 2. DoD

- [x] `/verify-email` и `/reset-password` публичны и не перехватываются
      защитой — ✅ (`App.tsx`, e2e-переход без токена).
- [x] Точные API-пути и DTO совпадают с backend — ✅
      (`backend/domains/auth/router.py`, `schemas.py`).
- [x] Vitest: успех и ошибка `VerifyEmailPage` — ✅ (7 passed всего).
- [x] Playwright: невалидный токен показывает ошибку — ✅ (17 passed).
- [x] `ci.ps1` — ✅ (339 passed + 3 skipped, ruff/mypy 0).
- [x] doc-lint `--tests-count auto` — ✅ (6 checks, 0 failed).
- [x] Аудит смешанных алфавитов — ✅ (0 находок).
- [x] `git diff --check` — ✅.

## 3. Что не сделано / блокеры

Нет. S-95 (live LRS/TTS) остаётся отложенным по внешним ключам и не
блокирует hotfix.

## 4. Отклонения от Design (нужен ADR?)

Нет. Добавлены публичные маршруты и вызовы существующих auth-эндпоинтов;
контракты не менялись.

## 5. Новые факты → Design (обязаны вернуться в Design?)

Маршруты `/verify-email`, `/reset-password`, `/login` и поведение
`X-Forwarded-For` на edge (только `$remote_addr`) стоит отразить в
разделе фронтенда/edge при следующей ревизии Design; отдельных ADR не
требуется.

## 6. Риски

- Страницы зависят от срока жизни токена: истёкший токен показывает
  ошибку и предлагает войти; повторная отправка письма — существующий
  flow.
- `/login` — минимальная страница входа; регистрация по-прежнему через
  существующий API/UI-поток.

## 7. Следующий этап — S-101: Release v1.0.0

Платформа готова к **v1.0.0**: P0-блокер email-ссылок закрыт, staging
acceptance S-100 пройдена (8/8 OK), GPU-станция отвечает (57.4 ток/с),
CI/e2e/doc-lint зелёные. Остаётся S-101: зафиксировать приёмку, поднять
версию до `1.0.0`, выпустить release notes, тег `v1.0.0` и GHCR-образы,
поставить бейдж **Production Ready**. При незакрытом S-95 — письменное
решение владельца о выпуске с известным ограничением.
