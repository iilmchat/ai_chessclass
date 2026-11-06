"""S-77/S-82: конфигурация контура observability (dev + prod).

Проверяем «правду конфигов» без docker: YAML-парсинг, связи
Prometheus ↔ Alertmanager ↔ rules, профиль observability, TLS/retention,
entrypoint-рендер секретов и документацию runbook.
"""

import json
from pathlib import Path

import yaml

_MOUNT = Path("/repo")
ROOT = _MOUNT if (_MOUNT / "deploy").is_dir() else Path(__file__).resolve().parents[2]
OBS = ROOT / "deploy/observability"
PROD = OBS / "prod"

OBS_SERVICES = ("tempo", "otel-collector", "prometheus", "alertmanager", "grafana")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_otel_collector_and_compose_services():
    collector = _load(OBS / "otel-collector.yml")
    assert "otlp" in collector["receivers"]
    assert "otlphttp/tempo" in collector["exporters"]
    assert "prometheus" in collector["exporters"]
    assert "traces" in collector["service"]["pipelines"]

    tempo = _load(OBS / "tempo.yml")
    assert tempo["server"]["http_listen_port"] == 3200

    alerts = _load(OBS / "alerts.yml")
    exprs = [rule["expr"] for group in alerts["groups"] for rule in group["rules"]]
    assert any("histogram_quantile" in expr for expr in exprs)
    assert any("chessclass_failed_jobs" in expr for expr in exprs)

    for compose_name in ("docker-compose.dev.yml", "docker-compose.staging.yml"):
        text = (ROOT / compose_name).read_text(encoding="utf-8")
        for service in ("otel-collector", "tempo", "prometheus", "grafana"):
            assert service in text, (compose_name, service)


def test_grafana_dashboard_has_p95_errors_and_traces():
    dashboard = json.loads(
        (OBS / "grafana/dashboards/chessclass.json").read_text(encoding="utf-8")
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


# --- S-82: prod-контур -------------------------------------------------------


def test_prod_profile_is_opt_in_with_persistent_storage():
    compose = _load(ROOT / "docker-compose.prod.yml")
    services = compose["services"]
    for name in OBS_SERVICES:
        assert "observability" in services[name]["profiles"], name
        assert services[name]["container_name"].startswith("chessclass-prod-")
        assert "ccnet" in services[name]["networks"]
    # Базовый стек не попадает в профиль observability.
    assert "observability" not in services["api"].get("profiles", [])

    volumes = compose["volumes"]
    for volume in (
        "chessclass_prod_tempo",
        "chessclass_prod_prometheus",
        "chessclass_prod_alertmanager",
        "chessclass_prod_grafana",
    ):
        assert volume in volumes, volume

    # Tempo не публикует портов, доступы — только loopback.
    assert "ports" not in services["tempo"]
    assert "ports" not in services["otel-collector"]
    for name, port in (
        ("prometheus", "9092"),
        ("alertmanager", "9093"),
        ("grafana", "3002"),
    ):
        published = services[name]["ports"]
        assert any("127.0.0.1:" in item and port in item for item in published), name


def test_prod_containers_use_entrypoint_rendering():
    """Alertmanager/Prometheus не умеют env-expansion — секреты рендерит entrypoint."""
    compose = _load(ROOT / "docker-compose.prod.yml")
    services = compose["services"]
    # У alertmanager образ имеет ENTRYPOINT=/bin/alertmanager: command не годится.
    assert services["alertmanager"]["entrypoint"] == [
        "/bin/sh",
        "/etc/alertmanager/alertmanager-entrypoint.sh",
    ]
    assert "command" not in services["alertmanager"]
    assert services["prometheus"]["entrypoint"] == [
        "/bin/sh",
        "/etc/prometheus/prometheus-entrypoint.sh",
    ]
    # Коллектор distroless: healthcheck с shell/wget невозможен.
    assert "healthcheck" not in services["otel-collector"]
    # Grafana: без дефолтного admin/admin — пароль обязателен, анонимный вход выкл.
    env = services["grafana"]["environment"]
    assert ":?" in str(env["GF_SECURITY_ADMIN_PASSWORD"])
    assert env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    assert env["GF_SERVER_SERVE_FROM_SUB_PATH"] == "true"


def test_tempo_retention_and_mtls_on_otlp():
    tempo = _load(PROD / "tempo.yml")
    assert tempo["compactor"]["compaction"]["block_retention"] == "168h"
    assert tempo["usage_report"]["reporting_enabled"] is False
    otlp = tempo["distributor"]["receivers"]["otlp"]["protocols"]
    for protocol in ("http", "grpc"):
        tls = otlp[protocol]["tls"]
        assert tls["cert_file"].endswith("tempo.crt"), protocol
        assert tls["key_file"].endswith("tempo.key"), protocol
        assert tls["client_ca_file"].endswith("ca.crt"), protocol
    # HTTP API Tempo — plaintext внутри сети: Grafana читает без клиентского
    # сертификата, порт не публикуется (client_auth_type без него падает).
    assert "http_tls_config" not in tempo["server"]

    collector = _load(PROD / "otel-collector.yml")
    exporter = collector["exporters"]["otlp/tempo"]
    assert exporter["endpoint"] == "tempo:4317"
    assert exporter["tls"]["insecure"] is False
    # Клиент проверяет сертификат Tempo по внутреннему CA и предъявляет свой
    # (mTLS: Tempo сверяет его с client_ca_file).
    assert exporter["tls"]["ca_file"].endswith("ca.crt")
    assert exporter["tls"]["cert_file"].endswith("collector.crt")
    assert exporter["tls"]["key_file"].endswith("collector.key")
    assert "health_check" in collector["extensions"]


def test_prometheus_wires_rules_and_alertmanager():
    prom = (PROD / "prometheus.yml.tmpl").read_text(encoding="utf-8")
    # Правила и Alertmanager связаны (иначе алерты никуда не уходят).
    assert "/etc/prometheus-rules/alerts.yml" in prom
    assert "alertmanagers:" in prom
    assert "alertmanager:9093" in prom
    assert "__METRICS_TOKEN__" in prom  # рендерится entrypoint'ом
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "./deploy/observability/alerts.yml:/etc/prometheus-rules/alerts.yml:ro" in (
        compose
    )


def test_alertmanager_telegram_route_and_inhibit():
    config = _load(PROD / "alertmanager.yml.tmpl")
    assert config["templates"] == ["/etc/alertmanager/telegram.tmpl"]

    receivers = {item["name"]: item for item in config["receivers"]}
    assert set(receivers) == {"telegram", "telegram-critical"}
    for name in receivers:
        telegram = receivers[name]["telegram_configs"][0]
        assert telegram["bot_token"] == "__TELEGRAM_BOT_TOKEN__"
        assert telegram["chat_id"] == "__TELEGRAM_ALERT_CHAT_ID__"
        assert telegram["send_resolved"] is True
        assert telegram["parse_mode"] == "HTML"

    route = config["route"]
    assert route["receiver"] == "telegram"
    assert set(route["group_by"]) == {"alertname", "severity", "component"}
    assert route["group_wait"] == "30s"
    assert route["repeat_interval"] == "3h"
    children = {item["receiver"]: item for item in route["routes"]}
    assert children["telegram-critical"]["matchers"] == ['severity="critical"']
    assert children["telegram-critical"]["repeat_interval"] == "1h"
    assert children["telegram"]["matchers"] == ['severity="warning"']
    assert children["telegram"]["repeat_interval"] == "6h"

    # Inhibit: critical гасит warning того же alertname/component,
    # ApiDown гасит остальные api-алерты.
    inhibit = config["inhibit_rules"]
    assert len(inhibit) == 2
    assert inhibit[0]["source_matchers"] == ['severity="critical"']
    assert inhibit[0]["target_matchers"] == ['severity="warning"']
    assert inhibit[0]["equal"] == ["alertname", "component"]
    assert inhibit[1]["source_matchers"] == ['alertname="ChessClassApiDown"']
    assert inhibit[1]["equal"] == ["component"]

    template = (PROD / "telegram.tmpl").read_text(encoding="utf-8")
    assert 'define "telegram.chessclass"' in template
    assert "Annotations.summary" in template


def test_alerts_cover_required_signals():
    alerts = _load(OBS / "alerts.yml")
    rules = {
        rule["alert"]: rule for group in alerts["groups"] for rule in group["rules"]
    }
    for name in (
        "ChessClassApiDown",
        "ChessClassHighErrorRate",
        "ChessClassP95LatencyHigh",
        "ChessClassDLQGrowth",
        "ChessClassDLQGrowthRate",
    ):
        assert name in rules, name
    for rule in rules.values():
        assert rule["labels"]["severity"] in {"warning", "critical"}
        assert rule["labels"]["component"] in {"api", "worker"}
        assert rule["annotations"]["summary"]
        assert rule["annotations"]["description"]
    # 5xx-rate и p95 считаются по HTTP-метрикам, DLQ — по счётчику failed_jobs.
    assert "5.." in rules["ChessClassHighErrorRate"]["expr"]
    assert "histogram_quantile" in rules["ChessClassP95LatencyHigh"]["expr"]
    assert "chessclass_failed_jobs > 10" in rules["ChessClassDLQGrowth"]["expr"]
    assert "delta(chessclass_failed_jobs" in rules["ChessClassDLQGrowthRate"]["expr"]
    assert rules["ChessClassApiDown"]["expr"].strip() == 'up{job="chessclass-api"} == 0'


def test_entrypoints_and_cert_script():
    alertmanager_entrypoint = (PROD / "alertmanager-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert alertmanager_entrypoint.startswith("#!/bin/sh")
    assert "set -eu" in alertmanager_entrypoint
    assert "umask 077" in alertmanager_entrypoint
    assert "TELEGRAM_BOT_TOKEN:?" in alertmanager_entrypoint
    assert "amtool check-config" in alertmanager_entrypoint
    assert "chmod 600" in alertmanager_entrypoint

    prometheus_entrypoint = (PROD / "prometheus-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert "promtool check config" in prometheus_entrypoint
    assert "__METRICS_TOKEN__" in prometheus_entrypoint
    assert "--storage.tsdb.retention.time" in prometheus_entrypoint

    # Секреты не логируются: entrypoint не печатает значения env.
    assert "echo \"$TELEGRAM_BOT_TOKEN\"" not in alertmanager_entrypoint

    cert_script = (ROOT / "scripts/gen-internal-certs.ps1").read_text(encoding="utf-8")
    assert "alpine/openssl" in cert_script
    assert "clientAuth" in cert_script
    assert "DNS:tempo" in cert_script and "DNS:otel-collector" in cert_script

    gitignore = (ROOT / "deploy/internal-certs/.gitignore").read_text(encoding="utf-8")
    assert "*.key" in gitignore and "*.crt" in gitignore


def test_env_examples_document_observability():
    prod_env = (ROOT / ".env.prod.example").read_text(encoding="utf-8")
    for key in (
        "GRAFANA_ADMIN_USER",
        "GRAFANA_ADMIN_PASSWORD",
        "GRAFANA_ROOT_URL",
        "PROMETHEUS_PORT",
        "ALERTMANAGER_PORT",
        "GRAFANA_PORT",
        "TELEGRAM_ALERT_CHAT_ID",
        "TELEGRAM_BOT_TOKEN",
        "METRICS_TOKEN",
        "OTEL_ENABLED",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        assert f"{key}=" in prod_env, key
    assert "CHANGE_ME_GRAFANA_PASSWORD" in prod_env
    # Grafana-пароль обязателен и для prod-compose (иначе config -q падает).
    dev_env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "GRAFANA_ADMIN_PASSWORD=" in dev_env


def test_edge_serves_grafana_without_csp_duplicate():
    edge = (ROOT / "deploy/nginx/edge.conf").read_text(encoding="utf-8")
    assert "location /grafana/" in edge
    assert "proxy_pass http://grafana:3000;" in edge
    assert "X-Forwarded-Prefix /grafana" in edge
    # CSP излучает web-nginx; дубликат на edge ломает S-61 (test_csp_conf).
    assert "Content-Security-Policy" not in edge


def test_runbooks_document_alerts_and_duty():
    operations = (ROOT / "docs/runbooks/operations.md").read_text(encoding="utf-8")
    assert "Prod-observability" in operations
    assert "TELEGRAM_ALERT_CHAT_ID" in operations
    assert "amtool" in operations
    assert "gen-internal-certs.ps1" in operations
    incident = (ROOT / "docs/incident-response.md").read_text(encoding="utf-8")
    assert "Алерты и дежурство" in incident
    assert "Alertmanager" in incident
