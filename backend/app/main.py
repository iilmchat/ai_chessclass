import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis_lib
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.routers import healthz, readyz
from core.config import settings
from core.db import engine
from core.errors import register_exception_handlers
from core.logging import new_request_id, request_id_var, setup_logging
from core.security import jwks
from domains.anticheat.router import router as anticheat_router
from domains.audit.router import router as audit_router
from domains.auth.router import admin_router as auth_admin_router
from domains.auth.router import router as auth_router
from domains.bot_lab.router import admin_router as bot_admin_router
from domains.bot_lab.router import router as bots_router
from domains.chess_lab.router import router as chess_router
from domains.classes.router import router as classes_router
from domains.cognitive.router import router as skills_router
from domains.export.router import router as export_router
from domains.lms.router import router as lms_router
from domains.observability.router import admin_router as observability_admin_router
from domains.observability.router import metrics_router
from domains.profile.router import router as profile_router
from domains.progress.router import router as progress_router
from domains.python_teacher.router import router as py_router
from domains.reports.router import router as reports_router
from domains.studies.router import admin_router as studies_admin_router
from domains.studies.router import router as studies_router
from domains.tournaments.router import admin_router as tournaments_admin_router
from domains.tournaments.router import router as tournaments_router
from domains.voice.router import router as voice_router
from llm.router import router as llm_admin_router
from rag.router import router as rag_admin_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
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


app = FastAPI(
    title="ChessClass API",
    version="0.2.1",
    description=(
        "Единая экосистема «Шахматно-программистский класс» (ChessClass). "
        "Архитектура — Design.md; контракты — docs/SPEC.md."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3200",
        "http://web:3200",
        "http://localhost:3201",
    ],
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
app.include_router(profile_router, prefix="/api/v1")
app.include_router(progress_router, prefix="/api/v1")
app.include_router(py_router, prefix="/api/v1")
app.include_router(chess_router, prefix="/api/v1")
app.include_router(classes_router, prefix="/api/v1")
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
