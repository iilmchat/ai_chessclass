"""Фикстуры и общие хелперы: in-process app (lifespan), уникальные email,
очистка данных, прямое создание пользователей, seeds+admin-клиент.

Тесты идут в реальный dev-стек (localhost:5438/6384, ADR-013) — RULES §6.
"""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
import redis.asyncio as redis_lib
import sqlalchemy as sa
from asgi_lifespan import LifespanManager

from app.main import app
from core.config import settings
from core.db import engine, session_factory
from core.levels import Level
from core.security import hash_password
from domains.auth.models import EmailToken, EmailTokenKind, User, UserRole
from domains.profile.models import UserProfile

API = "/api/v1"
PASSWORD = "Passw0rd!123"

_CLEAN_IPS = ("127.0.0.1", "testclient", "unknown")
_seeds_done = False


def pytest_configure(config: pytest.Config) -> None:
    """Тесты герметичны: не ходим в живой RouterAI/LM Studio из dev-.env."""
    _ = config
    settings.llm_base_url = ""
    settings.llm_api_key = ""
    settings.llm_local_fallback = False


@pytest.fixture
def redis_client():
    """Клиент Redis для тестов экономики/квот (закрывается после теста)."""
    client = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return client


@pytest.fixture
def worker_role(monkeypatch):
    """APP_ROLE=worker — для сценариев с Stockfish (§15.3)."""
    monkeypatch.setattr(settings, "app_role", "worker")


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
        # Сначала зависимые строки, потом e2e-юзеры (FK SET NULL не удалит).
        await session.execute(
            sa.text(
                "DELETE FROM chess_studies WHERE created_by IN "
                "(SELECT id FROM users WHERE email LIKE '%@e2e.chessclass')"
            )
        )
        await session.execute(
            sa.text("DELETE FROM users WHERE email LIKE '%@e2e.chessclass'")
        )
        await session.execute(
            sa.text("DELETE FROM py_assignments WHERE slug LIKE 'test-%'")
        )
        await session.execute(
            sa.text("DELETE FROM audit_logs WHERE actor_email LIKE '%@e2e.chessclass'")
        )
        await session.commit()
    redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    try:
        keys: list[str] = []
        for ip in _CLEAN_IPS:
            keys += [f"auth:fail:{ip}", f"auth:lock:{ip}"]
        keys += await redis.keys("rl:*")
        keys += await redis.keys("quota:*")
        if keys:
            await redis.delete(*keys)
    finally:
        await redis.aclose()
    # pytest-asyncio даёт каждому тесту новый event-loop; пул engine хранит
    # соединения asyncpg, привязанные к loop'у теста, — dispose перед следующим
    await engine.dispose()


# --- общие хелперы (используются тестами нескольких доменов)

async def fetch_email_token(email: str, kind: EmailTokenKind = EmailTokenKind.VERIFY) -> str:
    """Неиспользованный email-токен из БД («консольный SMTP» пишет в логи)."""
    stmt = (
        sa.select(EmailToken)
        .where(EmailToken.kind == kind, EmailToken.used_at.is_(None))
        .join(User, EmailToken.user_id == User.id)
        .where(User.email == email)
    )
    async with session_factory() as session:
        row = (await session.execute(stmt)).scalar_one()
        return str(row.token)


async def register_verified(client: httpx.AsyncClient, email: str) -> dict:
    """Регистрация + подтверждение email; возвращает тело register-ответа."""
    response = await client.post(
        f"{API}/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201
    body = dict(response.json())
    token = await fetch_email_token(email)
    response = await client.post(f"{API}/auth/verify", json={"token": token})
    assert response.status_code == 200
    return body


async def make_direct_user(
    email: str, role: UserRole = UserRole.STUDENT, level: Level = Level.NOVICE
) -> int:
    """Пользователь напрямую в БД (верифицирован) — для RBAC-сценариев."""
    async with session_factory() as session:
        user = User(
            email=email,
            password_hash=hash_password(PASSWORD),
            role=role,
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        await session.flush()
        session.add(UserProfile(user_id=user.id, level=level))
        await session.commit()
        return int(user.id)


async def login(client: httpx.AsyncClient, email: str) -> tuple[httpx.AsyncClient, str, int]:
    """Логин; возвращает (client, accessToken, user_id)."""
    response = await client.post(
        f"{API}/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return client, str(body["accessToken"]), int(body["user"]["id"])


async def ensure_seeds() -> None:
    """Однократный прогон seeds (идемпотентен) — для admin-фикстуры."""
    global _seeds_done
    if _seeds_done:
        return
    from db.seeds import run as seeds_run

    await seeds_run()
    _seeds_done = True


@pytest.fixture
async def admin_client(make_client):
    """Клиент, залогиненный сид-админом (email/password из core.config)."""
    await ensure_seeds()
    client = await make_client()
    response = await client.post(
        f"{API}/auth/login",
        json={
            "email": settings.seed_admin_email,
            "password": settings.seed_admin_password,
        },
    )
    assert response.status_code == 200, response.text
    token = str(response.json()["accessToken"])
    client.headers["Authorization"] = f"Bearer {token}"
    return client
