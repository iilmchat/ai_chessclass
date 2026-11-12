# Runbook: LLM-шлюз (RouterAI / LM Studio)

**Область:** S-31, Design §8.3–§8.5. Относится к `api` и `worker`
(единый gateway), админ-эндпоинтам `/admin/models`, `/admin/llm/health`,
`/admin/finops/usage`.

## 1. Конфигурация

Все значения — в корневом `.env` (в git не коммитится). Dev-compose передаёт
его в `api`, `worker`, `migrate`, `seed` через `env_file`.

| Переменная | RouterAI | LM Studio (локально) |
|---|---|---|
| `LLM_BASE_URL` | `https://routerai.ru/api/v1` | `http://host.docker.internal:8034/v1` (Docker) или `http://127.0.0.1:8034/v1` (backend на хосте) |
| `LLM_API_KEY` | ключ RouterAI | пусто (LM Studio не проверяет) |
| `LLM_MODEL_*` | полные id из `GET /v1/models` | id загруженной модели, например `qwen/qwen3-4b-2507` |
| `LLM_COST_*` | ₽/1M из каталога | `0` |
| `LLM_LOCAL_FALLBACK` | `false` (cloud — основной) | `false` (local — основной) |

`LLM_BASE_URL` обязан включать `/v1`. Для LM Studio в Docker включите
**Serve on Local Network** (иначе контейнер не достучится до loopback хоста).

**S-96:** local-провайдер может быть внешней GPU-станцией:
`LLM_LOCAL_BASE_URL=http://172.18.0.1:8035/v1`, `LLM_LOCAL_MODEL` — id из
`GET /v1/models`, `LLM_LOCAL_API_KEY` — токен LM Studio (`Require Auth`).
Полная инструкция для Windows-станции — §6.

**Каталог сверён 2026-11-03** (RouterAI, 582 модели; цены ₽/1M input/output):

| Тир | Слаг | ₽/1M in | ₽/1M out |
|---|---|---|---|
| L1 | `qwen/qwen3.7-flash` | 3.1580 | 13.6845 |
| L2 | `deepseek/deepseek-v4.1-flash` | 10.4213 | 28.9480 |
| L3 | `anthropic/claude-sonnet-5.5` | 210.5308 | 1052.6542 |
| L3_alt | `x-ai/grok-4.7` | 210.5308 | 631.5925 |
| judge | `google/gemini-3.1-flash-lite` | 26.3164 | 157.8981 |

`reflection/beam-1.0-501b-*` в каталоге отсутствует (см. backlog TODO_V0.4).
При смене каталога обновить слаги/`LLM_COST_*` и повторить health/smoke.

## 2. Проверка

### 2.1. Health (admin)

```powershell
$login = Invoke-RestMethod http://127.0.0.1:8020/api/v1/auth/login `
  -Method Post -ContentType application/json `
  -Body (@{email='admin@chessclass.dev'; password='<seed-admin-password>'} | ConvertTo-Json)
Invoke-RestMethod http://127.0.0.1:8020/api/v1/admin/llm/health `
  -Headers @{Authorization="Bearer $($login.accessToken)"} | ConvertTo-Json -Depth 5
```

Ожидаемо: `status=ok`, `missingModels=[]`, все `tiers[].available=true`,
`lastCall.status=ok`. `echo` — `LLM_BASE_URL` пуст; `degraded` — провайдер
недоступен или слаги не найдены (смотрите `missingModels`).

### 2.2. Smoke LLM-шлюза: echo-базлайн → live (S-59)

Скрипт `backend/scripts/llm_smoke.py` — двурежимный: 4 маршрута (L1
`python_teacher.comment`, L2 `python_teacher.explain_code`, L3
`chess_lab.insight`, judge `anticheat.judge_explain`), health провайдера,
сверка FinOps (`llm_calls` + суммы за сутки), опционально озвучка (S-44) и
PDF-отчёт (S-25). Пишет `llm_calls` (`user_id=NULL`, квоты не расходуются).

Echo-базлайн (ключи не нужны — провайдер принудительно гасится):

```powershell
docker compose --env-file .env.staging -f docker-compose.staging.yml exec -T api `
  python scripts/llm_smoke.py --mode echo --with-voice --with-pdf `
  --out /srv/reports/llm-smoke-echo.json
```

Ожидаемо: exit 0, 4/4 `status=echo model=echo`, `cost=0.0000`,
`health=echo`, `voice=disabled` (graceful `voice_unavailable`), `pdf=ok`
(`%PDF-`). Артефакт — JSON schema `chessclass.llm_smoke/1`, baseline для
`--compare`.

Live-прогон (ключи `LLM_BASE_URL`/`LLM_API_KEY`; voice — `VOICE_API_KEY`):

```powershell
docker compose --env-file .env.staging -f docker-compose.staging.yml exec -T api `
  python scripts/llm_smoke.py --mode live --with-voice --with-pdf `
  --out /srv/reports/llm-smoke-live.json `
  --compare /srv/reports/llm-smoke-echo.json
```

Ожидаемо: exit 0, 4/4 `status=ok`, `health=ok`, `missingModels=[]`,
`cost>0`, per-route diff «echo → live». Без провайдера live-режим → exit 3;
провайдер недоступен/слаги не найдены → exit 2 (`health=degraded`).

Коды возврата: **0** — ожидания выполнены; **2** — расхождение
(route/health/voice/pdf); **3** — конфигурация (live без провайдера, нет
БД/Redis/артефакта). Проверено на staging **2026-11-03**: echo-базлайн
4/4 `status=echo` (cost 0), live 4/4 `status=ok` (cost 1.3629 ₽, health
`ok`, `missingModels=[]`); артефакты — `docs/sprint-reports/S-59-echo-baseline-
2026-11-03.json` и `S-59-live-2026-11-03.json`.

### 2.3. Строки FinOps

```powershell
docker compose -f docker-compose.dev.yml exec -T db psql -U chess -d chessclass `
  -c "select id,route,model_used,status,tokens_in,tokens_out,latency_ms from llm_calls order by id desc limit 8;"
```

## 3. Модели и цены

- Слаги — **полные** id RouterAI (`minimax/minimax-m3.1-flash`,
  `deepseek/deepseek-v4.1-flash`, `reflection/beam-1.0-501b-a23b`,
  `anthropic/claude-sonnet-5.5`, `google/gemini-3.1-flash-lite`).
- Цены — `pricing.prompt`/`pricing.completion` из `GET /v1/models` × 1 000 000
  (₽/1M). Обновлять при смене каталога; после изменения — перезапуск
  `api`/`worker`, затем health.
- `perplexity/pplx-decider-flash-v1.2` — decisions-API, не OpenAI chat:
  для judge-route не используется. Если нужен Decider, требуется отдельный
  адаптер (вне S-31).
- Reasoning-модели (MiniMax/DeepSeek/Beam) могут вернуть `content=null`,
  если `max_tokens` израсходован на reasoning. Провайдер делает retry и
  fallback; для стабильности не занижайте бюджет генерации.

## 4. Ротация ключа

1. Выпустить новый ключ в RouterAI, старый не отзывать до проверки.
2. Обновить `LLM_API_KEY` в `.env` (не в git, не в логах).
3. Перезапустить `api` и `worker` (dev: `docker compose ... restart api worker`;
   prod: `docker compose -f docker-compose.prod.yml up -d --force-recreate api worker`).
4. Проверить health и smoke; только после этого отозвать старый ключ.
5. При утечке — отозвать немедленно, проверить `llm_calls`/FinOps на аномалии.

## 5. Fallback, квоты, стоимость

Цепочка: **cloud RouterAI → local LM Studio (если `LLM_LOCAL_FALLBACK=true`)
→ echo**. В каждом шаге 1 retry с экспоненциальным backoff и jitter (S-70).
Перед шагом — circuit breaker в Redis: 5 ошибок за 60 с → OPEN, через 60 с →
HALF_OPEN с одним probe. Причина — в `llm_calls.fallback_from`
(`failover:cloud`/`failover:local` — ошибка, `failover:cb_open` — breaker
открыт, `failover:no_config` — нет ключа; `quota_exhausted`,
`quota_downgrade:{tier}` — квота).

- Квоты: free 50k / pro 500k токенов/день (UTC), Redis
  `quota:{user}:{YYYY-MM-DD}`; judge-route квоту не расходует.
- При исчерпании — echo или downgrade до L1; echo не пишет `usage_daily`.
- Стоимость: `cost_in/out` считаются по `LLM_COST_*`; ошибка записи FinOps
  не повторяет уже оплаченный LLM-вызов (S-31).
- **Latency (staging, 2026-11-03, первый вызов):** L1 25.7 с, L2 19.4 с,
  L3 11.1 с, judge 1.4 с. `LLM_TIMEOUT_S=40` — не занижать; при стабильно
  высоких значениях поднять до 60 с и/или прогревать провайдера.

## 5.1. Локальный LM Studio

1. Загрузить модель, включить **Serve on Local Network**, порт 8034.
2. `LLM_BASE_URL=http://host.docker.internal:8034/v1` (Docker) или
   `http://127.0.0.1:8034/v1` (backend на хосте).
3. Все `LLM_MODEL_*` = id из `GET /v1/models`; `LLM_COST_*=0`.
4. Проверить: `docker run --rm chessclass/backend:dev python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:8034/v1/models', timeout=5).read()[:200])"`.

## 6. GPU-инференс через обратный SSH (RTX 3060, Windows)

Станция: **Windows-ПК, NVIDIA RTX 3060 12 GB, 32 GB RAM, Xeon E5-2690 v3**,
LM Studio с моделью семейства `qwen-7b` (например,
`Qwen2.5-7B-Instruct`, Q4_K_M). L1/L2 идут в облако, при его отказе —
local LM Studio, затем echo.

**Архитектура:**

```text
[API/worker ChessClass (Docker)] -> http://172.18.0.1:8035/v1
          ^ (reverse SSH tunnel, bind на docker gateway)
[Сервер ChessClass] <- SSH <- [Windows + LM Studio 127.0.0.1:1234]
```

### Шаг 1. LM Studio на станции

1. Установить LM Studio, скачать `Qwen2.5-7B-Instruct` (Q4_K_M; 12 GB VRAM
   хватает с GPU offload всех слоёв, context 4096–8192).
2. Загрузить модель, открыть **Developer → Local Server**:
   - **Serve on Local Network** — включить;
   - порт **1234** (или 8034, если занят);
   - **Require Auth** — включить и сохранить токен (он же
     `LLM_LOCAL_API_KEY`).
3. Проверить на станции:

   ```powershell
   curl.exe http://127.0.0.1:1234/v1/models -H "Authorization: Bearer <token>"
   ```

   В ответе `data[].id` — точный id модели для `LLM_LOCAL_MODEL`.

### Шаг 2. SSH-клиент на Windows

1. Встроенный OpenSSH: `ssh -V` (Windows 10/11). Если нет — Settings →
   Optional Features → OpenSSH Client.
2. Ключ (без пароля в Scheduled Task):

   ```powershell
   ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_ed25519
   type $env:USERPROFILE\.ssh\id_ed25519.pub |
     ssh root@<IP-сервера> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
   ```

3. На сервере в `/etc/ssh/sshd_config`: `GatewayPorts clientspecified`,
   затем `systemctl reload ssh`.
4. Определить docker gateway (не всегда 172.18.0.1):

   ```bash
   docker network inspect chessclass-prod-net \
     --format '{{(index .IPAM.Config 0).Gateway}}'
   ```

5. Пробный туннель (окно оставить открытым):

   ```powershell
   ssh -N -R 172.18.0.1:8035:127.0.0.1:1234 root@<IP-сервера>
   ```

   `-R` пробрасывает локальный LM Studio на gateway сервера; порт 8035
   доступен контейнерам, но не публичному интернету.

### Шаг 3. Автозапуск с реконнектом

Скопировать `scripts/wg-gpu-tunnel.ps1` на станцию, например в
`C:\ChessClass\wg-gpu-tunnel.ps1`; запускать:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File C:\ChessClass\wg-gpu-tunnel.ps1 `
  -ServerHost <IP-сервера> -SshUser root
```

Скрипт проверяет `127.0.0.1:1234`, держит `ssh -N -R`, при обрыве ждёт
10 с и переподключается. LM Studio должен быть запущен до туннеля.

### Шаг 4. Scheduled Task (при входе в систему)

```powershell
schtasks /Create /SC ONLOGON /TN "ChessClass GPU Tunnel" `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\ChessClass\wg-gpu-tunnel.ps1 -ServerHost <IP-сервера> -SshUser root" `
  /RL HIGHEST /F
schtasks /Run /TN "ChessClass GPU Tunnel"
```

- Питание: `powercfg /change standby-timeout-ac 0`,
  `powercfg /change hibernate-timeout-ac 0`; отключить сон/гибернацию.
- Проверить: `Get-ScheduledTask -TaskName "ChessClass GPU Tunnel"`.

### Шаг 5. Проверка с сервера

```powershell
.\scripts\test-gpu-tunnel.ps1 `
  -BaseUrl http://172.18.0.1:8035/v1 `
  -ApiKey '<токен LM Studio>' `
  -Model qwen2.5-7b-instruct
```

Ожидаемо: `models` — список, `chat` — «Париж», `latency_ms`,
`tokens_per_second` (RTX 3060: ориентир 30–50 ток/с). Exit `0` — OK.
Скрипт не печатает ключ. Без PowerShell — `curl`:

```bash
curl -s http://172.18.0.1:8035/v1/models -H "Authorization: Bearer $LM_TOKEN"
```

### Шаг 6. Конфигурация ChessClass

```dotenv
LLM_LOCAL_FALLBACK=true
LLM_LOCAL_BASE_URL=http://172.18.0.1:8035/v1
LLM_LOCAL_MODEL=qwen2.5-7b-instruct   # точный id из GET /models
LLM_LOCAL_API_KEY=<токен LM Studio>
```

`LLM_MODEL_L1/L2` остаются облачными slug; `LLM_LOCAL_MODEL` задаёт модель
для LM Studio. Перезапустить `api` и `worker`. Проверить, что local
провайдер реально отвечает:

```bash
docker compose --env-file .env -f docker-compose.prod.yml exec -T api \
  python -c "import asyncio; from llm.gateway import get_local_provider; \
  print(asyncio.run(get_local_provider().list_models()))"
```

**Firewall:** если на сервере включён ufw, разрешить вход на gateway:8035
только из docker bridge (`ufw allow in on <docker-bridge> to 172.18.0.1
port 8035 proto tcp`); LM Studio не публиковать в интернет. На Windows
входящие 1234 не нужны — SSH идёт наружу.

**Отказоустойчивость:** при падении туннеля локальный шаг падает,
Circuit Breaker (S-70) после 5 ошибок открывает `cb:state:local`; шлюз
уходит в echo (`fallback_from=failover:local` / `failover:cb_open`).
Сон/выключение станции = временный отказ; Scheduled Task поднимет туннель
после входа.

## 7. Диагностика

| Симптом | Причина | Действие |
|---|---|---|
| `status=echo`, `providerConfigured=false` | пуст `LLM_BASE_URL` | заполнить `.env`, перезапустить |
| `status=degraded`, `missingModels` | неверный slug / нет модели | сверить с `GET /v1/models`, обновить `LLM_MODEL_*` |
| 401/403 от RouterAI | ключ неверен/отозван | ротация ключа (§4) |
| `content=null`, fallback | reasoning съел `max_tokens` | увеличить бюджет/не занижать; проверить `fallback_from` |
| `fallback_from=failover:cb_open` | breaker открыт после 5 ошибок за 60 с | проверить провайдера/ключ; сбросить `cb:*` в Redis только при ложном срабатывании |
| `password authentication failed` (dev DB) | пароль роли не совпал с volume | `ALTER USER chess WITH PASSWORD '<из .env>';` или пересоздать dev-volume |
| `Foreign key ... users` в standalone-скрипте | не импортированы auth-модели | импортировать `domains.auth.models` до запроса |
| embeddings всегда `hash` | пуст `LLM_EMBED_MODEL` | это ожидаемо; задать 768-мерную модель, если нужен провайдер |
| `voice=disabled` / 503 `voice_unavailable` | пуст `VOICE_API_KEY` или ElevenLabs geo-block (RU) | voice остаётся off; альтернативный TTS — backlog TODO_V0.4 |
