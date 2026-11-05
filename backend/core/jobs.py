"""DLQ arq-задач (S-73, ADR-016).

arq 0.28 не имеет callback `on_job_failure` с текстом исключения, поэтому
каждая задача оборачивается декоратором `track_job`: он открывает OTel-спан,
а при исключении делает upsert в `failed_jobs` и пробрасывает ошибку дальше
(arq сохраняет штатное поведение retry/result).
"""

import functools
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db import db_context, session_factory
from core.tracing import current_trace_id_optional, trace_context
from domains.observability.models import FailedJob

logger = logging.getLogger(__name__)

JobHandler = Callable[..., Awaitable[Any]]


def _json_safe(value: Any) -> Any:
    """Привести аргументы задачи к JSONB-совместимому виду."""
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return {"repr": repr(value)[:2000]}


async def record_failed_job(
    task: str,
    ctx: dict,
    args: tuple,
    kwargs: dict,
    exc: BaseException,
    trace_id: str | None = None,
) -> None:
    """Upsert последней ошибки задачи по `job_id`; сам никогда не роняет воркер."""
    job_id = str(ctx.get("job_id") or f"{task}:unknown")
    attempts = int(ctx.get("job_try") or 1)
    error = f"{type(exc).__name__}: {exc}"[:4000]
    try:
        async with db_context(None, "admin"):
            async with session_factory() as session:
                stmt = pg_insert(FailedJob).values(
                    job_id=job_id,
                    task=task,
                    args=_json_safe({"args": list(args), "kwargs": kwargs}),
                    error_type=type(exc).__name__[:128],
                    error=error,
                    attempts=attempts,
                    trace_id=trace_id,
                    status="failed",
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["job_id"],
                    set_={
                        "task": task,
                        "args": _json_safe({"args": list(args), "kwargs": kwargs}),
                        "error_type": type(exc).__name__[:128],
                        "error": error,
                        "attempts": attempts,
                        "trace_id": trace_id,
                        "status": "failed",
                        "failed_at": func.now(),
                    },
                )
                await session.execute(stmt)
                await session.commit()
    except Exception:  # noqa: BLE001 — DLQ не должен маскировать исходную ошибку
        logger.exception("dlq: не удалось записать failed_jobs task=%s job=%s", task, job_id)


def track_job(task_name: str) -> Callable[[JobHandler], JobHandler]:
    """Декоратор arq-задачи: trace-спан + запись исключения в DLQ."""

    def decorator(func: JobHandler) -> JobHandler:
        signature = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(ctx: dict, *args: Any, **kwargs: Any) -> Any:
            trace_id: str | None = None
            try:
                bound = signature.bind_partial(ctx, *args, **kwargs)
                candidate = bound.arguments.get("trace_id")
                if isinstance(candidate, str):
                    trace_id = candidate
            except TypeError:
                pass
            with trace_context(trace_id, span_name=f"arq.{task_name}"):
                try:
                    return await func(ctx, *args, **kwargs)
                except Exception as exc:
                    await record_failed_job(
                        task_name,
                        ctx,
                        args,
                        kwargs,
                        exc,
                        current_trace_id_optional(),
                    )
                    raise

        return wrapper

    return decorator
