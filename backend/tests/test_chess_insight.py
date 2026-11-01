"""S-11: инсайт позиции — факты SF + объяснение по уровню (worker-путь)."""

from pathlib import Path

import pytest
import sqlalchemy as sa

from core.config import settings
from tests.conftest import API, login, register_verified

pytestmark = pytest.mark.skipif(
    not Path(settings.stockfish_path).exists(),
    reason="Stockfish не установлен в образе",
)

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.fixture
def worker_role(monkeypatch):
    monkeypatch.setattr(settings, "app_role", "worker")


async def _insight(client, headers: dict, fen: str, level: str | None = None):
    payload = {"fen": fen}
    if level:
        payload["level"] = level
    return await client.post(
        f"{API}/chess/insight", json=payload, headers=headers
    )


async def test_insight_full_flow(admin_client, make_client, unique_email, worker_role):
    _ = admin_client
    client = await make_client()
    registered = await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    response = await _insight(client, headers, START_FEN)
    assert response.status_code == 200, response.text
    body = response.json()

    # факты SF: линии + материал, отдельно от объяснения
    assert body["facts"], "факты движка присутствуют"
    assert body["facts"][0]["moveUci"]
    assert any(f.startswith("Материал") for f in body["factsText"])
    # «LLM не правит факты»: объяснение — отдельное поле
    assert isinstance(body["explanation"], str) and body["explanation"]
    assert isinstance(body["knowledge"], list)  # S-39 RAG-блок
    assert body["level"] == "novice"  # уровень профиля (не advanced)

    # позиция сохранена (upsert) и видна в списке пользователя
    positions = await client.get(f"{API}/chess/positions", headers=headers)
    assert positions.status_code == 200
    items = positions.json()["items"]
    assert any(item["fen"] == START_FEN for item in items)
    meta = next(item["meta"] for item in items if item["fen"] == START_FEN)
    assert meta["explanation"] == body["explanation"]
    assert meta["level"] == "novice"
    _ = registered, user_id


async def test_insight_level_override(admin_client, make_client, unique_email, worker_role):
    _ = admin_client
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)

    response = await _insight(
        client, {"Authorization": f"Bearer {access}"}, START_FEN, level="advanced"
    )
    assert response.status_code == 200
    assert response.json()["level"] == "advanced"


async def test_insight_invalid_fen(admin_client, make_client, unique_email):
    _ = admin_client
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    response = await _insight(
        client, {"Authorization": f"Bearer {access}"}, "это не FEN"
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_fen"


async def test_insight_upsert_single_row(admin_client, make_client, unique_email, worker_role):
    _ = admin_client
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    await _insight(client, headers, START_FEN, level="novice")
    await _insight(client, headers, START_FEN, level="intermediate")  # тот же FEN

    from core.db import session_factory
    from domains.chess_lab.models import ChessPosition

    async with session_factory() as session:
        count = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(ChessPosition)
                .where(ChessPosition.user_id == user_id)
            )
        ).scalar_one()
    assert count == 1  # upsert по (user_id, fen)
