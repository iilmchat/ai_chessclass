# Observability v0.6 (S-77)

Локальный контур: **OTel Collector → Tempo (traces) / Prometheus (metrics) →
Grafana**. Профиль `observability` не стартует вместе с обычным dev-стеком.

## Запуск (dev)

```bash
# API/worker должны отправлять спаны в collector
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
docker compose -f docker-compose.dev.yml --profile observability up -d
```

- Grafana: http://localhost:3001 (`admin` / `admin`)
- Prometheus: http://localhost:9091
- OTLP HTTP: `localhost:4320` (внутри сети `otel-collector:4318`)
- OTLP gRPC: `localhost:4319` (`otel-collector:4317`)
- Tempo: только внутри сети (`tempo:3200`)

Для staging используйте `docker-compose.staging.yml --profile observability`:
Grafana `3002`, Prometheus `9092`, OTLP HTTP `4322`, gRPC `4321`.

## Dashboard

`grafana/dashboards/chessclass.json` (uid `chessclass-http-traces`):

- p95 latency by route из `chessclass_http_request_duration_seconds_bucket`;
- error rate 5xx/all из `chessclass_http_requests_total`;
- DLQ `chessclass_failed_jobs`;
- Tempo traces по `{service.name="chessclass-api"}`; в каждом trace виден
  `trace_id`, который также пишется в JSON-логи и `llm_calls.trace_id`.

Prometheus-алерты (`alerts.yml`): error rate > 5%, p95 latency > 2 s,
`chessclass_failed_jobs > 10`.

## Проверка конфигурации

```bash
docker compose -f docker-compose.dev.yml config -q
docker run --rm -v "$PWD/deploy/observability/otel-collector.yml:/etc/otelcol/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:0.164.0 validate --config=/etc/otelcol/config.yaml
```

Collector хранит traces в Tempo 24 часа (`block_retention`); Prometheus —
process-local метрики API (при нескольких репликах нужно скрейпить каждую).
