# Security-ревью (S-55)

**Дата:** 2026-11-03 · OWASP-чеклист, зависимости, secrets scan.

## 1. Итог

- **Critical/high:** не найдено.
- **Зависимости:** после `pip install --upgrade pip` — `pip-audit`:
  `No known vulnerabilities found` (сам пакет проекта не в PyPI — skip).
- **Secrets scan:** `git grep` по `sk-*`, `ghp_*`, `AIza*`, PEM-ключам —
  совпадений в трекаемых файлах нет; `.env` в `.gitignore`.
- **Security-заголовки:** добавлены `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`; HSTS — только `APP_ENV=prod`.

## 2. OWASP Top-10 (кратко)

| Категория | Статус | Меры |
|---|---|---|
| A01 Broken Access Control | ✅ | RBAC `require_role`, object-level проверки (submissions, rooms, cards); auditor scope |
| A02 Cryptographic Failures | ✅ | Argon2, RS256/JWKS, TLS runbook, секреты в env |
| A03 Injection | ✅ | SQLAlchemy параметры; sandbox RestrictedPython; CSP не задан |
| A04 Insecure Design | ⚠️ | rate-limit есть; consent/лимиты; нужен threat-model на staging |
| A05 Security Misconfiguration | ✅ | debug off в prod, CORS whitelist, headers, HSTS |
| A06 Vulnerable Components | ✅ | pip-audit чисто (после upgrade pip); обновлять образ |
| A07 Auth Failures | ✅ | lockout, refresh rotation/revoke, email verify, JWT alg whitelist |
| A08 Integrity Failures | ⚠️ | pip без hash-lock; добавить lock/constraints в S-56 |
| A09 Logging/Monitoring | ✅ | audit_logs, request_id, metrics/alerts; секреты не логируются |
| A10 SSRF | ⚠️ | внешние URL (LLM/LRS/Telegram) из env; allowlist/egress в prod |

## 3. Проверки

```powershell
# secrets (tracked files)
git grep -nE "(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,}|-----BEGIN (RSA |EC )?PRIVATE KEY-----)"

# зависимости (в контейнере)
docker compose -f docker-compose.dev.yml run --rm api sh -c \
  "pip install -q --upgrade pip pip-audit && pip-audit --format=columns"
```

## 4. Остаточные риски

- Нет CSP/`X-XSS-Protection` (последний устарел); CSP требует аудита
  inline-стилей/скриптов Vite.
- `python-multipart` не используется; импорт RAG — base64 JSON (лимит
  размера задаёт прокси).
- JWT private key — файл/volume; ротация и HSM не автоматизированы.
- Rate-limit Redis in-memory; при кластере нужен общий Redis (он общий).
- `pip` без hash-lock; supply-chain риск.
- Telegram token в URL API (httpx не логирует URL по умолчанию); нельзя
  включать debug-логи httpx в prod.

## 5. Рекомендации к S-56

1. `pip-compile --generate-hashes` + constraints для prod.
2. CSP report-only, затем enforce.
3. axe-core/playwright в CI (a11y).
4. Egress allowlist для LLM/LRS/Telegram.
5. Прогнать `pip-audit` на финальном образе RC.
