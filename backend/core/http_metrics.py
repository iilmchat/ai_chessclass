"""S-77: process-local HTTP RED-метрики для Prometheus/Grafana.

Гистограмма latency + счётчики status позволяют строить p95 и error-rate в
Grafana без отдельного SDK. Метрики process-local (как и `/metrics`), поэтому
при нескольких uvicorn-процессах Prometheus должен скрейпить каждый инстанс.
"""

import threading
from collections import defaultdict

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

_lock = threading.Lock()
_requests: dict[tuple[str, str, str], int] = defaultdict(int)
_histogram: dict[tuple[str, str], list[int]] = defaultdict(
    lambda: [0] * (len(BUCKETS) + 1)
)
_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
_duration_count: dict[tuple[str, str], int] = defaultdict(int)


def observe_http_request(
    method: str, route: str, status: int, duration_s: float
) -> None:
    """Учесть один HTTP-запрос (route — шаблон/путь, без query)."""
    key = (method.upper(), route)
    with _lock:
        _requests[(key[0], key[1], str(status))] += 1
        bucket_values = _histogram[key]
        for index, limit in enumerate(BUCKETS):
            if duration_s <= limit:
                bucket_values[index] += 1
        bucket_values[-1] += 1  # +Inf
        _duration_sum[key] += duration_s
        _duration_count[key] += 1


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render_http_metrics() -> str:
    """Prometheus text exposition для HTTP-метрик."""
    lines: list[str] = [
        "# HELP chessclass_http_requests_total HTTP requests by status",
        "# TYPE chessclass_http_requests_total counter",
    ]
    with _lock:
        for (method, route, status), count in sorted(_requests.items()):
            lines.append(
                "chessclass_http_requests_total"
                f'{{method="{_escape(method)}",route="{_escape(route)}",'
                f'status="{status}"}} {count}'
            )
        lines.extend(
            [
                "# HELP chessclass_http_request_duration_seconds HTTP latency",
                "# TYPE chessclass_http_request_duration_seconds histogram",
            ]
        )
        for (method, route), buckets in sorted(_histogram.items()):
            labels = f'method="{_escape(method)}",route="{_escape(route)}"'
            for index, limit in enumerate(BUCKETS):
                lines.append(
                    "chessclass_http_request_duration_seconds_bucket"
                    f'{{{labels},le="{limit}"}} {buckets[index]}'
                )
            lines.append(
                "chessclass_http_request_duration_seconds_bucket"
                f'{{{labels},le="+Inf"}} {buckets[-1]}'
            )
            lines.append(
                "chessclass_http_request_duration_seconds_sum"
                f'{{{labels}}} {_duration_sum[(method, route)]:.6f}'
            )
            lines.append(
                "chessclass_http_request_duration_seconds_count"
                f'{{{labels}}} {_duration_count[(method, route)]}'
            )
    return "\n".join(lines) + "\n"


def reset_http_metrics() -> None:
    """Для тестов: очистить process-local счётчики."""
    with _lock:
        _requests.clear()
        _histogram.clear()
        _duration_sum.clear()
        _duration_count.clear()
