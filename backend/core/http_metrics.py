"""S-77/S-92: HTTP RED-метрики для Prometheus/Grafana.

S-92: при `PROMETHEUS_MULTIPROC_DIR` используется multiprocess-режим
prometheus_client: каждый uvicorn-воркер пишет свои счётчики в общий каталог,
а `/metrics` собирает их через `MultiProcessCollector`. Это устраняет потерю
3/4 трафика при `--workers 4`. Без env-переменной работает обычный
process-local registry (dev/CI).
"""

import os
from pathlib import Path

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

#: le-бакеты в секундах: 5ms … 10s.
BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

_MULTIPROC = bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR", "").strip())
if _MULTIPROC:
    Path(os.environ["PROMETHEUS_MULTIPROC_DIR"]).mkdir(parents=True, exist_ok=True)
    _render_registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(_render_registry)
else:
    _render_registry = REGISTRY

# В multiprocess-режиме значения пишутся в файлы; локальные объекты нужны
# только для API инкремента. В single-process они же отдают /metrics.
_requests = Counter(
    "chessclass_http_requests",
    "HTTP requests by status",
    ["method", "route", "status"],
)
_duration = Histogram(
    "chessclass_http_request_duration_seconds",
    "HTTP latency",
    ["method", "route"],
    buckets=BUCKETS,
)


def observe_http_request(
    method: str, route: str, status: int, duration_s: float
) -> None:
    """Учесть один HTTP-запрос (route — шаблон/путь, без query)."""
    labels = {"method": method.upper(), "route": route}
    _requests.labels(**labels, status=str(status)).inc()
    _duration.labels(**labels).observe(duration_s)


def render_http_metrics() -> str:
    """Prometheus text exposition (multiprocess-агрегат при включении)."""
    return generate_latest(_render_registry).decode("utf-8")


def mark_process_dead() -> None:
    """Убрать файлы завершившегося воркера из multiprocess-каталога."""
    if _MULTIPROC:
        multiprocess.mark_process_dead(os.getpid())


def reset_http_metrics() -> None:
    """Совместимость тестов: счётчики prometheus_client не сбрасываются.

    В тестах проверяется наличие серий, а не точные значения; между тестами
    registry живёт в процессе и это ожидаемо.
    """
