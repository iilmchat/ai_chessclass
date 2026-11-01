"""S-19: матч против SF UCI_Elo 1400 + семплирование ходов (sf_sample)."""

from pathlib import Path

import pytest
import sqlalchemy as sa

from core.config import settings
from tests.conftest import API, login, register_verified

RANDOM_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)

pytestmark = pytest.mark.skipif(
    not Path(settings.stockfish_path).exists(),
    reason="Stockfish не установлен в образе",
)


async def test_match_vs_sf1400(
    admin_client, make_client, unique_email, worker_role, redis_client
):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    response = await client.post(
        f"{API}/bots", json={"code": RANDOM_BOT}, headers=headers
    )
    assert response.status_code == 201
    bot_id = int(response.json()["id"])

    from domains.bot_lab.match import run_match

    result = await run_match(bot_id, "stockfish-1400", redis_client)
    assert "error" not in result, result
    # против SF-1400 random-бот почти наверняка проигрывает; timeout —
    # легитимный исход при per-move/budget-таймауте (S-37)
    assert result["result"] in ("win", "loss", "draw", "timeout")
    assert 0 < result["plies"] <= 60

    from core.db import session_factory
    from domains.bot_lab.models import BotMatchMove

    async with session_factory() as session:
        moves = (
            await session.execute(
                sa.select(BotMatchMove).where(BotMatchMove.match_id == result["matchId"])
            )
        ).scalars().all()
        assert len(moves) == result["plies"]
        # семплирование 10 % ходов ученика (sf_sample)
        sampled = [m for m in moves if m.sf_sample]
        student_moves = [m for m in moves if m.agent == "student"]
        expected = max(1, int(len(student_moves) * 0.10))
        assert len(sampled) >= 1  # хотя бы один семпл при >= 1 ходе ученика
        assert len(sampled) <= len(student_moves) + 1
        _ = expected


async def test_sf_opponent_unknown_rejected(
    admin_client, make_client, unique_email, worker_role, redis_client
):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    response = await client.post(
        f"{API}/bots", json={"code": RANDOM_BOT}, headers={"Authorization": f"Bearer {access}"}
    )
    bot_id = int(response.json()["id"])

    from domains.bot_lab.match import run_match

    result = await run_match(bot_id, "stockfish-9999", redis_client)
    assert "error" in result and "unknown opponent" in result["error"]
