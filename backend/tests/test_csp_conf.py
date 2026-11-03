"""S-61: CSP — release-truth проверки конфигураций nginx (аналог doc-lint).

Файлы nginx/compose лежат в корне репо: в контейнере backend виден только
backend/ — на CI (полный checkout) и локально проверки работают; иначе skip.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

requires_repo_root = pytest.mark.skipif(
    not (ROOT / "frontend/nginx.conf").is_file()
    or not (ROOT / "docker-compose.prod.yml").is_file(),
    reason="корень репо недоступен (контейнер backend)",
)

CSP_MARK = 'add_header Content-Security-Policy "default-src \'self\';'


@requires_repo_root
def test_web_nginx_emits_csp_enforce():
    """Web-nginx (образ prod/e2e) держит enforce-заголовок CSP."""
    conf = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    assert CSP_MARK in conf, "frontend/nginx.conf: нет enforce-заголовка CSP"
    assert "Content-Security-Policy-Report-Only" not in conf, (
        "frontend/nginx.conf в образе — enforce; report-only делает "
        "docker-entrypoint.d/40-csp.sh по CSP_MODE"
    )


@requires_repo_root
def test_csp_mode_report_only_switch_exists():
    """Механизм Report-Only: скрипт entrypoint + опция staging-контура."""
    script = (ROOT / "frontend/docker-entrypoint.d/40-csp.sh").read_text(
        encoding="utf-8"
    )
    assert "CSP_MODE:-enforce" in script
    assert "add_header Content-Security-Policy-Report-Only " in script

    staging = (ROOT / "docker-compose.staging.yml").read_text(encoding="utf-8")
    assert "CSP_MODE: report-only" in staging

    prod = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "CSP_MODE" not in prod  # в prod enforce по умолчанию


@requires_repo_root
def test_edge_conf_does_not_duplicate_csp():
    """Edge не дублирует CSP (заголовок излучается web-nginx, проходит сквозь)."""
    edge = (ROOT / "deploy/nginx/edge.conf").read_text(encoding="utf-8")
    assert "Content-Security-Policy" not in edge, (
        "edge.conf: CSP приходит от web-nginx; добавление на edge даст дубликат"
    )
