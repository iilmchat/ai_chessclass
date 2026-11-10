# Observability: dev-контур (S-77) и prod-профиль (S-82)

Локальный/дев-контур: **OTel Collector → Tempo (traces) / Prometheus
(metrics) → Grafana**. Профиль `observability` не стартует вместе с обычным
dev-стеком. Prod-контур (S-82): те же компоненты + **Alertmanager →
Telegram/email** с TLS/mTLS и persistent storage; S-87 добавляет маскировку
логов, второй email-receiver и node-exporter для алерта о диске; эксплуатация —
`docs/runbooks/operations.md` §10, алерты и дежурство —
`docs/incident-response.md` §4.1.

## Запуск (dev)

```bash
# API/worker должны отправлять спаны в collector
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
docker compose -f docker-compose.dev.yml --profile observability up -d
```

- Grafana: http://localhost:3001 (`admin` / `admin` — только dev)
- Prometheus: http://localhost:9091
- OTLP HTTP: `localhost:4320` (внутри сети `otel-collector:4318`)
- OTLP gRPC: `localhost:4319` (`otel-collector:4317`)
- Tempo: только внутри сети (`tempo:3200`)

Для staging используйте `docker-compose.staging.yml --profile observability`:
Grafana `3002`, Prometheus `9092`, OTLP HTTP `4322`, gRPC `4321`.
(В prod-профиле те же номера host-портов, но контейнеры `chessclass-prod-*`.)

## Prod-профиль (S-82)

Отличия от dev-контура (конфиги — `deploy/observability/prod/`):

| Что | Dev (S-77) | Prod (S-82) |
|---|---|---|
| Запуск | `--profile observability` | `--profile observability` + `.env` с секретами |
| Tempo retention | 24 h (ephemeral) | **168 h (7 дней)**, volume `chessclass_prod_tempo` |
| Tempo storage | без volume | `chessclass_prod_tempo:/var/tempo` |
| Collector → Tempo | plaintext | **mTLS** (внутренний CA, `scripts/gen-internal-certs.ps1`) |
| Prometheus | rules в конфиге | rules `alerts.yml` + `alerting → alertmanager:9093`, retention 15 d, volume |
| Alertmanager | нет | Telegram + email (`telegram_configs`/`email_configs`), группировка, inhibit rules |
| node-exporter | нет | метрики диска volumes профиля, алерт `ChessClassObservabilityDiskFull` |
| Grafana | admin/admin, host-порт | пароль обязателен, анонимный вход выкл., только loopback + edge `/grafana/` |
| Публикация портов | loopback | Tempo/collector — **не публикуются**; Prometheus/Alertmanager/Grafana — только `127.0.0.1` |

Секреты не пишутся в конфиги: Alertmanager и Prometheus рендерят
`*.tmpl` в `/tmp` (chmod 600) при старте — `alertmanager-render.sh`
(вызывается `alertmanager-entrypoint.sh`), `prometheus-entrypoint.sh`. Логи
Alertmanager дополнительно проходят `redact-logs.awk` (bot token/Bearer →
`<REDACTED>`), но остаются чувствительными (TTL — runbook §10.10).

### Быстрая проверка prod-контура

```powershell
# только конфиги (promtool/amtool, без запуска контейнеров)
.\scripts\observability-selftest.ps1

# + runtime smoke: профиль, targets, маршруты, mTLS-трейс, Grafana; затем stop
.\scripts\observability-selftest.ps1 -Stack
```

Runtime smoke использует **фиктивные** `TELEGRAM_BOT_TOKEN` и chat_id: доставка
в реальный чат проверяется вручную (`operations.md` §10.6). Скрипт
останавливает только контейнеры профиля (`stop`), volumes сохраняются.

## Dashboard

`grafana/dashboards/chessclass.json` (uid `chessclass-http-traces`):

- p95 latency by route из `chessclass_http_request_duration_seconds_bucket`;
- error rate 5xx/all из `chessclass_http_requests_total`;
- DLQ `chessclass_failed_jobs`;
- Tempo traces по `{service.name="chessclass-api"}`; в каждом trace виден
  `trace_id`, который также пишется в JSON-логи и `llm_calls.trace_id`.

Prometheus-алерты (`alerts.yml`, 10 правил): `ChessClassApiDown`,
`ChessClassHighErrorRate` (5xx > 5 %), `ChessClassP95LatencyHigh` (> 2 s),
`ChessClassDLQGrowth` (`chessclass_failed_jobs > 10`),
`ChessClassDLQGrowthRate` (рост DLQ),
`ChessClassObservabilityDiskFull` (<10% на `/var/tempo`),
`ChessClassEmailOutboxStuck` (oldest pending > 1 ч),
`ChessClassRetentionArchiveStale` (архив > 8 дней),
`ChessClassBackupFailed` (бэкап > 25 ч),
`ChessClassBackupRestoreFailed` (restore-test failed). Маршруты: `critical →
telegram-critical,email` (повтор 1 ч), `warning → telegram,email` (повтор
6 ч); email включается при `SMTP_HOST` + `ALERT_EMAIL_TO`; inhibit — critical
гасит warning того же alertname/component, `ChessClassApiDown` гасит остальные
api-алерты.

## Проверка конфигурации

```bash
docker compose -f docker-compose.dev.yml config -q
docker compose --env-file .env.prod.example -f docker-compose.prod.yml config -q
docker run --rm -v "$PWD/deploy/observability/otel-collector.yml:/etc/otelcol/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:0.164.0 validate --config=/etc/otelcol/config.yaml
# правила и рендер конфигов prod — см. scripts/observability-selftest.ps1
```

Collector хранит traces в Tempo: dev — 24 часа, prod — 7 дней; Prometheus —
process-local метрики API (при нескольких репликах нужно скрейпить каждую),
prod — retention 15 дней в volume `chessclass_prod_prometheus`.

## Ограничения

- Alertmanager не умеет env-expansion в конфиге — используется рендер из
  шаблона; при ошибке рендера контейнер падает осознанно (алерты не теряются
  молча).
- При ошибке доставки в Telegram библиотека печатает URL вида
  `https://api.telegram.org/bot<TOKEN>/sendMessage`; S-87 маскирует его
  (`bot<REDACTED>`) построчным awk-фильтром. Шаблоны узкие, поэтому логи всё
  равно чувствительны (доступ и TTL — `docs/runbooks/operations.md` §10.10).
- Email-receiver требует STARTTLS (обычно 587); implicit TLS 465 Alertmanager
  не поддерживает — используйте relay/порт 587.
- mTLS — только на OTLP-приёмниках Tempo; HTTP API Tempo — plaintext внутри
  сети без публикации порта (Grafana читает по нему без клиентского cert).
