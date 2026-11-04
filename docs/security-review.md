# Security-ревью (S-55, обновлено S-71)

**Дата:** 2026-11-03 · **Обновление:** 2026-11-04 (S-71) · OWASP-чеклист,
зависимости, secrets scan, OWASP LLM Top 10.

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

## 5. OWASP LLM Top 10 — меры S-71

| Категория | Статус | Меры |
|---|---|---|
| LLM01 Prompt Injection | ✅ | Структурная изоляция trusted/untrusted в `builder.py`; санитизация служебных токенов и role-меток; adversarial-тесты |
| LLM02 Insecure Output Handling | ✅ | `guard_llm_output` нейтрализует опасный HTML/JS; API отдаёт JSON, React рендерит текст без `dangerouslySetInnerHTML` |
| LLM03 Supply Chain | ⚠️ | hash-lock + `pip-audit` (S-62); ревизия LLM-зависимостей — регулярно |
| LLM04 Model DoS | ⚠️ | квоты/лимиты токенов и таймауты; token-aware rate limits — бэклог |
| LLM05 Vector/Embedding Weaknesses | ⚠️ | retrieval только `published`, RAG-блок изолирован как untrusted; provenance источников — в развитии |
| LLM06 Sensitive Information Disclosure | ✅ | Редактирование секретоподобных строк в промпте и ответе; логи без текста промптов/ответов |
| LLM07 Insecure Plugin Design | n/a | tool-calling/плагинов у LLM нет |
| LLM08 Excessive Agency | ⚠️ | LLM только генерирует текст; действия выполняет backend по RBAC |
| LLM09 Overreliance | ⚠️ | античит — только флаги, финальное решение за учителем (ADR-005) |
| LLM10 Model Theft | n/a | модели внешних провайдеров, весов локально нет |

**LLM01 (Prompt Injection).** `llm/prompts/builder.py` собирает
user-сообщение из четырёх блоков: `<trusted_instructions>`,
`<trusted_facts>`, `<untrusted_user_input>`, `<untrusted_rag_context>`.
Код и вопрос ученика больше не попадают в trusted facts (в т.ч. в
`anticheat/judge.py`). `llm/security.py` санитизирует `<|im_start|>`,
`<|im_end|>`, `[INST]`, `<<SYS>>`, role-метки (`system:`, `assistant:`),
JSON-роль и попытки закрыть trusted-теги. Системный промпт всех маршрутов
содержит `SECURITY_RULES`; `PROMPT_VERSIONS` поднят до 2. Матрица атак —
`backend/tests/test_prompt_injection.py`.

**LLM02 (Insecure Output Handling).** `guard_llm_output` в gateway
нейтрализует `<script>/<iframe>/<img>/<svg>/…`, `on*`-обработчики,
`javascript:` и `data:text/html`; в лог пишутся только имена находок, без
содержимого ответа. Фронтенд не использует `dangerouslySetInnerHTML` —
ответы отображаются как текст, поэтому HTML не исполняется.

**LLM06 (Sensitive Information Disclosure).** `redact_secrets` заменяет
`sk-*`, `ghp_*`, `github_pat_*`, `AIza*`, Bearer-токены, PEM-ключи и
присваивания `api_key/secret/password/token` как во входящем промпте, так
и в ответе модели. Секреты не логируются; диагностика output guard
содержит только категории находок.

**CI-гейты RAG (S-71).** После seeds в `.github/workflows/ci.yml` и
`scripts/ci.ps1` блокирующе запускаются `scripts/chess_rag_eval.py`
(MISS → exit 1) и `scripts/rag_gold_check.py` (мёртвый gold-кейс → exit 1).

## 6. Рекомендации к S-56

1. `pip-compile --generate-hashes` + constraints для prod.
2. CSP report-only, затем enforce.
3. axe-core/playwright в CI (a11y).
4. Egress allowlist для LLM/LRS/Telegram.
5. Прогнать `pip-audit` на финальном образе RC.
