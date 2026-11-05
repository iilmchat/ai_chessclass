"""Сквозная трассировка S-73 (ADR-017): HTTP → arq → LLM.

`trace_id` хранится в ContextVar и дублируется в OTel-контекст как remote
parent. Это позволяет:
  * писать `trace_id` в JSON-логи API и воркера;
  * передавать его аргументом arq-задачи;
  * сохранять его в `llm_calls` и связывать FinOps-строку с запросом.

OTel SDK включается в lifespan API/воркера. Если `OTEL_ENABLED=false` или
экспортёр не задан, спаны создаются, но никуда не отправляются (no-op
экспорт); это безопасно для CI и dev без коллектора.
"""

import logging
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from core.config import settings

logger = logging.getLogger(__name__)

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")
_tracer = trace.get_tracer("chessclass")
_configured = False


def get_tracer(name: str = "chessclass") -> trace.Tracer:
    """Трейсер для ручных спанов (HTTP, arq, LLM)."""
    return trace.get_tracer(name)


def new_trace_id() -> str:
    """32 hex-символа, совместимо с W3C trace-id (не all-zero)."""
    return secrets.token_hex(16)


def is_valid_trace_id(value: str | None) -> bool:
    if not value or len(value) != 32:
        return False
    try:
        return int(value, 16) != 0
    except ValueError:
        return False


def current_trace_id() -> str:
    """Текущий trace_id: явный контекст приоритетнее активного OTel-спана."""
    explicit = _trace_id_var.get()
    if explicit != "-":
        return explicit
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        return f"{span_context.trace_id:032x}"
    return "-"


def current_trace_id_optional() -> str | None:
    """trace_id для БД: `None` вместо заглушки `-`."""
    value = current_trace_id()
    return None if value == "-" else value


def _span_context(trace_id: str) -> SpanContext:
    # span_id родителя нужен только для W3C-совместимости; уникальность
    # в пределах trace не критична, но исключаем 0.
    span_id = secrets.randbits(64) or 1
    return SpanContext(
        trace_id=int(trace_id, 16),
        span_id=span_id,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )


@contextmanager
def trace_context(
    trace_id: str | None = None, *, span_name: str | None = None
) -> Iterator[str]:
    """Установить trace_id и (опционально) открыть именованный спан."""
    if trace_id and is_valid_trace_id(trace_id):
        tid = trace_id
    else:
        tid = new_trace_id()
    token: Token[str] = _trace_id_var.set(tid)
    parent = NonRecordingSpan(_span_context(tid))
    try:
        # NonRecordingSpan делает trace_id текущим для вложенных спанов,
        # включая вызовы LLM внутри задачи.
        with trace.use_span(parent, end_on_exit=False):
            if span_name:
                with _tracer.start_as_current_span(span_name):
                    yield tid
            else:
                yield tid
    finally:
        _trace_id_var.reset(token)


def trace_id_from_headers(headers: Any) -> str | None:
    """Достать trace_id из `traceparent` или `x-trace-id` (если валиден)."""
    traceparent = headers.get("traceparent", "")
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) >= 4 and is_valid_trace_id(parts[1]):
            return str(parts[1])
    value = headers.get("x-trace-id", "")
    return str(value) if is_valid_trace_id(value) else None


def setup_tracing() -> None:
    """Инициализировать OTel SDK один раз на процесс."""
    global _configured
    if _configured:
        return
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:  # pragma: no cover — lock должен содержать SDK
        logger.warning("otel: SDK не установлен — трассировка остаётся no-op")
        return

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "deployment.environment": settings.app_env,
            }
        )
    )
    endpoint = settings.otel_exporter_otlp_endpoint or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", ""
    )
    if settings.otel_enabled and endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        logger.info("otel: OTLP exporter → %s", endpoint)
    trace.set_tracer_provider(provider)
    _configured = True
