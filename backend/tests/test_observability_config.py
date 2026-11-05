"""S-77: конфигурация OTel Collector, Tempo, Prometheus и Grafana."""

import json
from pathlib import Path

import yaml

_MOUNT = Path("/repo")
ROOT = _MOUNT if (_MOUNT / "deploy").is_dir() else Path(__file__).resolve().parents[2]


def test_otel_collector_and_compose_services():
    collector = yaml.safe_load(
        (ROOT / "deploy/observability/otel-collector.yml").read_text(
            encoding="utf-8"
        )
    )
    assert "otlp" in collector["receivers"]
    assert "otlphttp/tempo" in collector["exporters"]
    assert "prometheus" in collector["exporters"]
    assert "traces" in collector["service"]["pipelines"]

    tempo = yaml.safe_load(
        (ROOT / "deploy/observability/tempo.yml").read_text(encoding="utf-8")
    )
    assert tempo["server"]["http_listen_port"] == 3200

    alerts = yaml.safe_load(
        (ROOT / "deploy/observability/alerts.yml").read_text(encoding="utf-8")
    )
    exprs = [
        rule["expr"]
        for group in alerts["groups"]
        for rule in group["rules"]
    ]
    assert any("histogram_quantile" in expr for expr in exprs)
    assert any("chessclass_failed_jobs" in expr for expr in exprs)

    for compose_name in ("docker-compose.dev.yml", "docker-compose.staging.yml"):
        text = (ROOT / compose_name).read_text(encoding="utf-8")
        for service in ("otel-collector", "tempo", "prometheus", "grafana"):
            assert service in text, (compose_name, service)


def test_grafana_dashboard_has_p95_errors_and_traces():
    dashboard = json.loads(
        (ROOT / "deploy/observability/grafana/dashboards/chessclass.json").read_text(
            encoding="utf-8"
        )
    )
    expressions = [
        target.get("expr", "")
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    ]
    assert any("histogram_quantile(0.95" in expr for expr in expressions)
    assert any("chessclass_http_requests_total" in expr for expr in expressions)
    assert any(
        "trace_id" in panel.get("title", "").lower()
        for panel in dashboard["panels"]
    )
    assert any(panel.get("type") == "traces" for panel in dashboard["panels"])
