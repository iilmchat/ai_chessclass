import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis_lib
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.routers import healthz, readyz
from core.config import settings
from core.db import ALLOWED_DB_ROLES, db_context, engine
from core.error_tracking import init_sentry
from core.errors import register_exception_handlers
from core.http_metrics import mark_process_dead, observe_http_request
from core.logging import new_request_id, request_id_var, setup_logging
from core.security import decode_token, jwks
from core.tracing import (
    get_tracer,
    setup_tracing,
    trace_context,
    trace_id_from_headers,
)
from domains.anticheat.router import router as anticheat_router
from domains.audit.router import router as audit_router
from domains.auth.router import admin_router as auth_admin_router
from domains.auth.router import router as auth_router
from domains.bot_lab.router import admin_router as bot_admin_router
from domains.bot_lab.router import router as bots_router
from domains.chess_lab.router import router as chess_router
from domains.classes.router import router as classes_router
from domains.cognitive.router import router as skills_router
from domains.consent.router import router as consent_router
from domains.export.router import router as export_router
from domains.lms.router import router as lms_router
from domains.observability.router import admin_router as observability_admin_router
from domains.observability.router import metrics_router
from domains.profile.router import router as profile_router
from domains.progress.router import router as progress_router
from domains.pvp.router import admin_router as pvp_admin_router
from domains.pvp.router import router as pvp_router
from domains.python_teacher.router import router as py_router
from domains.reports.router import router as reports_router
from domains.retention.router import holds_router as legal_holds_router
from domains.retention.router import users_router as retention_users_router
from domains.review.router import router as review_router
from domains.studies.router import admin_router as studies_admin_router
from domains.studies.router import router as studies_router
from domains.telegram.router import router as telegram_router
from domains.tournaments.router import admin_router as tournaments_admin_router
from domains.tournaments.router import router as tournaments_router
from domains.voice.router import router as voice_router
from llm.router import router as llm_admin_router
from rag.router import router as rag_admin_router

logger = logging.getLogger(__name__)
init_sentry("chessclass-api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    setup_tracing()
    # S-58: в staging/prod localhost-источники почти наверняка означают
    # незаданный CORS_ORIGINS — предупреждаем, но не роняем старт.
    if settings.app_env in ("staging", "prod") and any(
        "localhost" in origin for origin in settings.cors_origins
    ):
        logger.warning(
            "cors: localhost-origins в %s — проверьте CORS_ORIGINS", settings.app_env
        )
    # S-90: legacy HS256 — только переходный режим. В prod/staging не роняем
    # старт (совместимость), но предупреждаем явно.
    if settings.app_env in ("staging", "prod"):
        if settings.jwt_legacy_hs256:
            logger.warning(
                "auth: JWT_LEGACY_HS256=true в %s — отключите legacy HS256",
                settings.app_env,
            )
        if settings.jwt_algorithm.upper() != "RS256":
            logger.warning(
                "auth: JWT_ALGORITHM=%s в %s — целевой режим RS256/JWKS",
                settings.jwt_algorithm,
                settings.app_env,
            )
        if settings.jwt_algorithm.upper() == "RS256" and not (
            settings.jwt_private_key or settings.jwt_private_key_path
        ):
            logger.warning(
                "auth: RS256 без JWT_PRIVATE_KEY(_PATH) — токены не подпишутся"
            )
    app.state.redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    # бутстрап LLM: сверка слагов моделей с провайдером (Design §8.3, R-01);
    # неуспех не роняет старт (S-05 добавит fallback-цепочку cloud→local→echo)
    if settings.llm_base_url:
        try:
            from llm.bootstrap import validate_model_slags

            await validate_model_slags()
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm bootstrap failed: %s", exc)
    else:
        logger.warning("llm: LLM_BASE_URL не задан — LLM-маршруты недоступны")
    yield
    from llm.gateway import close_llm_providers

    await close_llm_providers()
    await app.state.redis.aclose()
    await engine.dispose()
    # S-92: убрать multiprocess-файлы завершившегося uvicorn-воркера.
    mark_process_dead()


app = FastAPI(
    title="ChessClass API",
    version="1.0.1",
    description=(
        "Единая экосистема «Шахматно-программистский класс» (ChessClass). "
        "Архитектура — Design.md; контракты — docs/SPEC.md."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id") or new_request_id()
    token = request_id_var.set(request_id)
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["x-request-id"] = request_id
    return response


def _db_principal(request: Request) -> tuple[int | None, str]:
    """Достать принципала из access-JWT; иначе fail-closed anonymous."""
    scheme, _, raw = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not raw.strip():
        return None, "anonymous"
    payload = decode_token(raw.strip())
    if payload is None:
        return None, "anonymous"
    sub, role = payload.get("sub"), payload.get("role")
    if (
        not isinstance(sub, str)
        or not sub.isdigit()
        or not isinstance(role, str)
        or role not in ALLOWED_DB_ROLES
        or role == "anonymous"
    ):
        return None, "anonymous"
    return int(sub), role


@app.middleware("http")
async def db_context_middleware(request: Request, call_next) -> Response:
    """S-72: RLS-контекст запроса на всё время обработки (сброс в finally)."""
    user_id, role = _db_principal(request)
    async with db_context(user_id, role):
        return await call_next(request)


@app.middleware("http")
async def tracing_middleware(request: Request, call_next) -> Response:
    """S-73: trace_id из W3C/x-trace-id или новый; спан на HTTP-запрос."""
    trace_id = trace_id_from_headers(request.headers)
    with trace_context(trace_id) as tid:
        with get_tracer("chessclass.http").start_as_current_span("http.request") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", request.url.path)
            response = await call_next(request)
            span.set_attribute("http.status_code", response.status_code)
        response.headers["x-trace-id"] = tid
        return response


@app.middleware("http")
async def http_metrics_middleware(request: Request, call_next) -> Response:
    """S-77: latency/status для p95/error-rate в Prometheus/Grafana."""
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", request.url.path)
        observe_http_request(
            request.method, route, status, time.perf_counter() - started
        )


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next) -> Response:
    """S-55: базовые security-заголовки (OWASP secure headers)."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    if settings.app_env == "prod":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


# S-90: реальный IP из X-Forwarded-For доверенного edge/web. Middleware
# добавляется последним, поэтому выполняется до request_id/tracing/DB-context.
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=settings.proxy_trusted_hosts,
)

register_exception_handlers(app)


@app.get("/.well-known/jwks.json", include_in_schema=False)
async def well_known_jwks() -> dict:
    return jwks()

# healthz — и от корня (Design §15.3: GET /healthz), и под /api/v1 (для прокси фронтенда)
app.include_router(healthz.router, tags=["health"])
app.include_router(healthz.router, prefix="/api/v1", include_in_schema=False)
app.include_router(readyz.router, tags=["health"])
app.include_router(readyz.router, prefix="/api/v1", include_in_schema=False)

# домены API v1 (Design §12.2)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(auth_admin_router, prefix="/api/v1")
app.include_router(legal_holds_router, prefix="/api/v1")
app.include_router(retention_users_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(progress_router, prefix="/api/v1")
app.include_router(py_router, prefix="/api/v1")
app.include_router(chess_router, prefix="/api/v1")
app.include_router(classes_router, prefix="/api/v1")
app.include_router(consent_router, prefix="/api/v1")
app.include_router(skills_router, prefix="/api/v1")
app.include_router(bots_router, prefix="/api/v1")
app.include_router(bot_admin_router, prefix="/api/v1")
app.include_router(anticheat_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(llm_admin_router, prefix="/api/v1")
app.include_router(rag_admin_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(studies_router, prefix="/api/v1")
app.include_router(studies_admin_router, prefix="/api/v1")
app.include_router(telegram_router, prefix="/api/v1")
app.include_router(pvp_router, prefix="/api/v1")
app.include_router(pvp_admin_router, prefix="/api/v1")
app.include_router(review_router, prefix="/api/v1")
app.include_router(tournaments_router, prefix="/api/v1")
app.include_router(tournaments_admin_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")
app.include_router(lms_router, prefix="/api/v1")
app.include_router(observability_admin_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(metrics_router)


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=settings.app_env == "dev",
        log_config=None,
    )


if __name__ == "__main__":
    run()
