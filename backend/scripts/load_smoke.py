"""S-55: нагрузочный smoke — p50/p95 health/ready и базовых read-endpoint.

Не запускает LLM/Stockfish/матчи (они async и внешние); профиль фиксируется
в docs/load-profile.md. Запуск в контейнере api:

  python scripts/load_smoke.py --base-url http://localhost:8020 \
      --requests 50 --concurrency 10 --p95-ms 150
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

import httpx


async def _one(client: httpx.AsyncClient, path: str) -> tuple[int, float]:
    started = time.perf_counter()
    try:
        response = await client.get(path)
        return response.status_code, (time.perf_counter() - started) * 1000
    except httpx.HTTPError:
        return 0, (time.perf_counter() - started) * 1000


async def run(
    base_url: str,
    requests: int,
    concurrency: int,
    p95_ms: float,
    include_ready: bool = False,
) -> dict:
    paths = ["/healthz"] + (["/readyz"] if include_ready else [])
    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[int, float, str]] = []

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:

        async def worker(index: int) -> None:
            path = paths[index % len(paths)]
            async with sem:
                status, elapsed = await _one(client, path)
            results.append((status, elapsed, path))

        await asyncio.gather(*(worker(i) for i in range(requests)))

    durations = sorted(elapsed for _status, elapsed, _path in results)
    errors = sum(1 for status, _elapsed, _path in results if status != 200)
    p50 = statistics.median(durations) if durations else 0.0
    p95 = durations[int(len(durations) * 0.95) - 1] if durations else 0.0
    report = {
        "baseUrl": base_url,
        "requests": requests,
        "concurrency": concurrency,
        "errors": errors,
        "p50Ms": round(p50, 1),
        "p95Ms": round(p95, 1),
        "targetP95Ms": p95_ms,
        "passed": errors == 0 and p95 <= p95_ms,
        "paths": paths,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8020")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--p95-ms", type=float, default=150.0)
    parser.add_argument("--include-ready", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(
        run(
            args.base_url,
            args.requests,
            args.concurrency,
            args.p95_ms,
            args.include_ready,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
