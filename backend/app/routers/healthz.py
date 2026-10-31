import asyncio
import logging

from fastapi import APIRouter, Request
from sqlalchemy import text
from core.base import CamelModel
from core.db import engine

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthOut(CamelModel):
    status: str
    db: bool
    redis: bool


async def _ping_db() -> bool:
    try:
        async with asyncio.timeout(2.0):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 — health никогда не роняет endpoint
        logger.warning("healthz: db ping failed: %s", exc)
        return False


async def _ping_redis(app: object) -> bool:
    client = getattr(app, "state", None) and getattr(app.state, "redis", None)
    if client is None:
        return False
    try:
        return bool(await asyncio.wait_for(client.ping(), 1.5))
    except Exception as exc:  # noqa: BLE001
        logger.warning("healthz: redis ping failed: %s", exc)
        return False


@router.get("/healthz", summary="Liveness: DB+Redis ping (Design §15.3)")
async def healthz(request: Request) -> HealthOut:
    db_ok = await _ping_db()
    redis_ok = await _ping_redis(request.app)
    return HealthOut(
        status="ok" if db_ok and redis_ok else "degraded",
        db=db_ok,
        redis=redis_ok,
    )
