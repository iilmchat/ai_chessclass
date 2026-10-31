"""`/readyz` — полные детали готовности (Design §15.3).

В отличие от liveness `/healthz` (DB+Redis ping), здесь: совпадение ревизии
alembic с head, версия приложения. SF/LLM-пинги добавляются в E-02/E-04.
"""

import asyncio
import logging

from fastapi import APIRouter, Request
from sqlalchemy import text

from app import __version__
from core.base import CamelModel
from core.db import engine

logger = logging.getLogger(__name__)

router = APIRouter()


class DbDetails(CamelModel):
    ok: bool
    revision: str | None
    head: str | None
    migrationsUpToDate: bool | None


class ReadyOut(CamelModel):
    status: str
    version: str
    db: DbDetails
    redis: bool


def _alembic_head() -> str | None:
    """Ожидаемая head-ревизия из дерева миграций (каталог относительно cwd)."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(Config("alembic.ini"))
        return str(script.get_current_head())
    except Exception:  # noqa: BLE001 — readyz не падает, а сообщает
        return None


async def _db_details() -> DbDetails:
    revision: str | None = None
    ok = False
    try:
        async with asyncio.timeout(2.0):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                row = (await conn.execute(text("SELECT version_num FROM alembic_version"))).first()
                revision = row[0] if row else None
        ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("readyz: db check failed: %s", exc)
    head = _alembic_head()
    up_to_date = (revision == head) if (revision and head) else None
    return DbDetails(ok=ok, revision=revision, head=head, migrationsUpToDate=up_to_date)


async def _redis_ok(request: Request) -> bool:
    client = getattr(request.app.state, "redis", None)
    if client is None:
        return False
    try:
        return bool(await asyncio.wait_for(client.ping(), 1.5))
    except Exception as exc:  # noqa: BLE001
        logger.warning("readyz: redis ping failed: %s", exc)
        return False


@router.get("/readyz", summary="Readiness: DB-ревизия миграций + Redis (Design §15.3)")
async def readyz(request: Request) -> ReadyOut:
    db = await _db_details()
    redis_ok = await _redis_ok(request)
    ready = db.ok and db.migrationsUpToDate is True and redis_ok
    return ReadyOut(
        status="ready" if ready else "not-ready",
        version=__version__,
        db=db,
        redis=redis_ok,
    )
