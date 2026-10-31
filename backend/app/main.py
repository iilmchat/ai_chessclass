from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis_lib
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.routers import healthz
from core.config import settings
from core.db import engine
from core.errors import register_exception_handlers
from core.logging import new_request_id, request_id_var, setup_logging
from domains.auth.router import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    app.state.redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(
    title="ChessClass API",
    version="0.1.0.dev0",
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

# healthz — и от корня (Design §15.3: GET /healthz), и под /api/v1 (для прокси фронтенда)
app.include_router(healthz.router, tags=["health"])
app.include_router(healthz.router, prefix="/api/v1", include_in_schema=False)

# домены API v1 (Design §12.2)
app.include_router(auth_router, prefix="/api/v1")


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
