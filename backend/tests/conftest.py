"""Фикстуры: in-process app (lifespan), уникальные email, очистка данных.

Тесты идут в реальный dev-стек (localhost:5438/6384, ADR-013) — RULES §6.
"""

import uuid

import httpx
import pytest
import redis.asyncio as redis_lib
import sqlalchemy as sa
from asgi_lifespan import LifespanManager

from app.main import app
from core.config import settings
from core.db import engine, session_factory

API = "/api/v1"

_CLEAN_IPS = ("127.0.0.1", "testclient", "unknown")


@pytest.fixture
async def make_client():
    """Фабрика httpx-клиентов с общим транспортом (каждый — свежая cookie-jar)."""
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        clients: list[httpx.AsyncClient] = []

        async def _make() -> httpx.AsyncClient:
            client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
            clients.append(client)
            return client

        yield _make
        for client in clients:
            await client.aclose()


@pytest.fixture
def unique_email() -> str:
    return f"u{uuid.uuid4().hex[:10]}@e2e.chessclass"


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    async with session_factory() as session:
        await session.execute(
            sa.text("DELETE FROM users WHERE email LIKE '%@e2e.chessclass'")
        )
        await session.commit()
    redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    try:
        keys: list[str] = []
        for ip in _CLEAN_IPS:
            keys += [f"auth:fail:{ip}", f"auth:lock:{ip}"]
        keys += await redis.keys("rl:*")
        if keys:
            await redis.delete(*keys)
    finally:
        await redis.aclose()
    # pytest-asyncio даёт каждому тесту новый event-loop; пул engine хранит
    # соединения asyncpg, привязанные к loop'у теста, — dispose перед следующим
    await engine.dispose()
