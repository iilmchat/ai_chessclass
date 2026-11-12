# Release Notes — ChessClass v1.0.0 «Production Ready»

**Статус:** ✅ Выпущен · **Дата:** 2026-11-12 · **База:** v0.9.0 ·
**Тег:** `v1.0.0` · **Миграции:** `0036_s98_legal_hold` (36)

> **v1.0.0 — финальный мажорный релиз.** Платформа переведена в статус
> **Production Ready**: финальная staging-приёмка S-100 пройдена **8/8 OK**,
> CI/e2e/doc-lint зелёные, GHCR-образы опубликованы. Live LRS/TTS (S-95)
> выпущен как известное ограничение по письменному решению владельца и
> перенесён в бэклог v1.1.0.

## Что нового

### Edge/Auth Hardening (S-90)

- Реальный IP клиента за прокси (`X-Real-IP`/`X-Forwarded-For` из
  `$remote_addr`; клиентский заголовок не принимается), per-account
  lockout и rate-limit на edge (`429`).
- RS256/JWKS по умолчанию, `JWT_LEGACY_HS256=false`; refresh-токены —
  opaque, HttpOnly-cookie с ротацией и защитой от reuse.
- Argon2id, email-верификация, сброс пароля, RBAC `student/teacher/admin`.

### Object-level authorization / BOLA (S-91)

- Хелперы проверки владельца объекта; `403` на чужой ресурс вместо утечки
  данных; кросс-тенантные тесты для профиля, классов, ботов, партий,
  документов RAG и жалоб.

### CD, Observability, Error Tracking (S-77, S-82, S-87, S-92)

- GHCR-публикация immutable-образов по тегу и SHA, Sentry (PII off),
  logrotate, multiprocess-метрики.
- OTel Collector + Tempo + Prometheus + Alertmanager (Telegram/email),
  node-exporter и Grafana в prod-контуре; правила алертов и
  `observability-selftest.ps1`.

### SMTP, Backups, Sandbox (S-75, S-93, S-97)

- SMTP с STARTTLS/SSL, очередь `email_outbox`, SPF/DKIM/DMARC-контракт и
  `smtp-smoke.ps1`; enforcement email-верификации.
- Offsite-бэкапы в S3 (aes-256, lifecycle 30 дней), restore-test с
  проверкой users/alembic; ротация и retention архивов.
- Сетевая изоляция песочницы по умолчанию: `bwrap --unshare-net` под
  uid 1000 без `CAP_SYS_ADMIN`, `deploy/seccomp-sandbox.json`, fallback
  `unshare`/none с warning и флагами `network_isolation_enforced` /
  `network_backend`.

### Retention & Legal Hold (S-98)

- `email_outbox`: body scrub через 30 дней, удаление метаданных через 90,
  архив без body.
- `legal_holds` (миграция `0036`): API `/admin/legal-holds`, retention skip
  и audit; DSAR `/admin/users/{id}/erase` с `409` при активном hold.
- Gauges и алерты по legal hold и успешности retention.

### GPU Tunnel (S-96, S-100)

- Внешняя GPU-станция (Windows, RTX 3060 12 GB, LM Studio Qwen-2.5-7B)
  через reverse SSH-туннель; `LLM_LOCAL_MODEL`, `scripts/wg-gpu-tunnel.ps1`,
  `scripts/test-gpu-tunnel.ps1` (models/chat/latency/tokens-per-second).
- Fallback cloud → local → echo покрыт тестами; фактическая проверка — в
  staging acceptance S-100.

### Публичные страницы аутентификации (hotfix email-routes)

- **`/verify-email?token=…`** — подтверждение email по ссылке из письма:
  `POST /auth/verify`, состояния `loading`/`success`/`error`, кнопка
  «Перейти к входу». Невалидный/истёкший токен показывает понятную ошибку
  вместо пустой страницы.
- **`/reset-password?token=…`** — новый пароль: два поля, минимум
  8 символов и совпадение, `POST /auth/password-reset/confirm` с
  `newPassword`, состояния `loading`/`success`/`error`.
- **`/login`** — публичная страница входа, на которую ведут обе ссылки.
- API-клиент: `verifyEmail(token)`, `resetPassword(token, newPassword)`;
  маршруты вне `ProtectedRoute`. Vitest — успех/ошибка `VerifyEmailPage`;
  Playwright — невалидный токен.

## Staging Acceptance (S-100) — результаты

Приёмка проведена по runbook
[`docs/runbooks/final-acceptance.md`](runbooks/final-acceptance.md).

| Проверка | Результат |
|---|---|
| Staging acceptance | **8/8 OK**, critical — 0 |
| SMTP | SPF/DKIM/DMARC **pass**, письмо доставлено (не в Spam) |
| S3 backup + restore | бэкап загружен/расшифрован, restore в temp PG: **users=10**, alembic совпал |
| RS256/JWKS | `/.well-known/jwks.json` отдаёт ключ, legacy HS256 отклонён |
| `PROXY_TRUSTED_HOSTS` | доверенный прокси работает, чужой Host отклонён |
| GPU-туннель | RTX 3060 + LM Studio: **57.4 ток/с**, fallback cloud → local → echo |
| Observability | selftest пройден, critical-алертов нет |
| API/БД/Redis | `healthz`/`readyz` — ok, миграции up-to-date |

## Известные ограничения v1.0.0

- **S-95 (Live LRS/TTS) — отложен до v1.1.0.** Нет боевых ключей
  LRS/ElevenLabs и доступа к провайдерам, поэтому нельзя подтвердить
  OAuth2/refresh, квоты, rate-limit, стоимость TTS и доставку писем в
  реальный ящик. Контракты и fallback покрыты тестами (MockTransport);
  staging SMTP/SPF/DKIM/DMARC приёмка пройдена. Выпуск v1.0.0 с этим
  ограничением разрешён письменным решением владельца проекта.
- **Staging observability — без Alertmanager/node-exporter.** В staging
  поднят усечённый контур (Collector/Tempo/Prometheus/Grafana); полный
  набор с Alertmanager и node-exporter есть в prod-контуре (S-82, S-87).
- **GPU в staging — Tailscale IP.** Для staging использован адрес
  Tailscale; в prod рекомендуется вернуть reverse SSH-туннель по
  runbook [`docs/runbooks/llm-gateway.md`](runbooks/llm-gateway.md) §6
  (изолированный доступ без публикации станции).

## Обновление (prod)

1. Получить тег и образы:

   ```bash
   git fetch --tags
   git checkout v1.0.0
   docker pull ghcr.io/iilmchat/chessclass-backend:v1.0.0
   docker pull ghcr.io/iilmchat/chessclass-frontend:v1.0.0
   ```

2. Обновить `.env`:

   ```dotenv
   IMAGE_TAG=1.0.0
   ```

3. Применить миграции и перезапустить сервисы:

   ```bash
   docker compose --env-file .env -f docker-compose.prod.yml run --rm migrate
   docker compose --env-file .env -f docker-compose.prod.yml up -d
   ```

4. Проверить готовность и smoke:

   ```bash
   curl -fsS http://127.0.0.1:8020/healthz
   curl -fsS http://127.0.0.1:8020/readyz
   .\scripts\smoke-prod.ps1 -EdgeBase https://<host>
   ```

5. **Откат:** вернуть `IMAGE_TAG=0.9.0`, `docker compose ... up -d`;
   миграция `0036_s98_legal_hold` обратно совместима (down-revision
   `0035_s97_*`). Полный порядок — `docs/runbooks/operations.md`.

> **Важно:** до завершения workflow `publish` тег `v1.0.0` в GHCR может
> отсутствовать. Дождитесь зелёного run и проверьте digest.

## Проверки

- Backend: **342** собранных теста (339 passed + 3 skipped), ruff/mypy — 0.
- Frontend: **7 passed** (Vitest), `tsc`/`vite build` — OK.
- UI-e2e: **17 passed** (Playwright).
- `ci.ps1`, `e2e.ps1 test`, `smtp-smoke.ps1`, `observability-selftest.ps1`
  (static), `pip-audit` (`No known vulnerabilities found`), doc-lint
  (6 checks, 0 failed), аудит алфавитов (0), `git diff --check` — зелёные.
- Миграции: Alembic head **0036_s98_legal_hold** (36).
