# Release Notes — ChessClass v1.0.0 (черновик)

**Статус:** 🔶 Черновик · **Дата выпуска:** после S-101 · **База:** v0.9.0

> Релиз **v1.0.0** выпускается только после успешной финальной приёмки
> S-100 (`docs/runbooks/final-acceptance.md`) и решения владельца по S-95.
> До тега `v1.0.0` версия в коде остаётся `0.9.0`.

## Что нового

### Публичные страницы аутентификации (hotfix email-routes)

- **`/verify-email?token=…`** — подтверждение email по ссылке из письма:
  токен из query, `POST /auth/verify`, состояния `loading`/`success`/`error`,
  кнопка «Перейти к входу». Невалидный или истёкший токен показывает
  понятную ошибку вместо пустой страницы.
- **`/reset-password?token=…`** — установка нового пароля по ссылке:
  два поля, проверка минимум 8 символов и совпадения, вызов
  `POST /auth/password-reset/confirm` с `newPassword`, состояния
  `loading`/`success`/`error`.
- **`/login`** — публичная страница входа, на которую ведут обе ссылки.
- API-клиент: `verifyEmail(token)` и `resetPassword(token, newPassword)`;
  маршруты добавлены в публичную секцию React Router (без `ProtectedRoute`).
- Тесты: Vitest — успех и ошибка `VerifyEmailPage`; Playwright — невалидный
  токен на `/verify-email` показывает «Токен недействителен».

### Финальная приёмка S-100

- Staging acceptance пройдена: **8/8 OK** (SMTP, S3/restore, RS256/JWKS,
  `PROXY_TRUSTED_HOSTS`, GPU-туннель, observability, API/БД/Redis).
- GPU-станция (RTX 3060, LM Studio Qwen-2.5-7B) отвечает через туннель:
  **57.4 ток/с**, fallback cloud → local → echo проверен.
- Чек-лист и troubleshooting — `docs/runbooks/final-acceptance.md`.

## Известные ограничения

- **S-95 (live LRS/TTS):** отложен — нет боевых ключей LRS/ElevenLabs.
  Выпуск v1.0.0 с этим ограничением возможен только по письменному
  решению владельца проекта.

## Проверки

- Backend: **342** собранных теста (339 passed + 3 skipped).
- Frontend: **7 passed** (Vitest).
- UI-e2e: **17 passed** (Playwright).
- `ci.ps1`, `e2e.ps1 test`, doc-lint, pip-audit, аудит алфавитов — зелёные.
