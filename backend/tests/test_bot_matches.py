"""S-18: матч-луп — матч до конца ≤120 c, Elo-дельта, записи матчей."""

from decimal import Decimal

import sqlalchemy as sa

from core.db import session_factory
from domains.bot_lab.elo import elo_delta
from domains.bot_lab.models import BotMatch, BotStats
from tests.conftest import API, login, register_verified

RANDOM_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)


def test_elo_delta_clamped_and_signed():
    assert elo_delta(Decimal("1000"), Decimal("1000"), "win") == Decimal("16.0")
    assert elo_delta(Decimal("1000"), Decimal("1000"), "loss") == Decimal("-16.0")
    assert elo_delta(Decimal("1000"), Decimal("1000"), "draw") == Decimal("0.0")
    # кламп ±40 (ADR-008)
    big = elo_delta(Decimal("2000"), Decimal("800"), "win")
    assert abs(big) <= Decimal("40")


async def test_match_vs_random_completes(
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

    # матч напрямую (тело задачи воркера) — детерминированно в тестах
    from domains.bot_lab.match import run_match

    result = await run_match(bot_id, "random", redis_client)
    assert "error" not in result, result
    assert result["result"] in ("win", "loss", "draw")
    assert 0 < result["plies"] <= 60

    async with session_factory() as session:
        match = (
            await session.execute(
                sa.select(BotMatch).where(BotMatch.user_id == user_id)
            )
        ).scalar_one()
        assert match.result.value == result["result"]
        assert match.finished_at is not None
        stats = await session.get(BotStats, user_id)
        assert stats is not None
        assert float(stats.elo) == result["elo"]


async def test_match_run_returns_real_match_id(
    admin_client, make_client, unique_email, monkeypatch
):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    response = await client.post(
        f"{API}/bots", json={"code": RANDOM_BOT}, headers=headers
    )
    bot_id = int(response.json()["id"])

    class FakePool:
        async def enqueue_job(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def aclose(self):
            return None

    async def fake_create_pool(*args, **kwargs):
        return FakePool()

    monkeypatch.setattr("arq.connections.create_pool", fake_create_pool)
    response = await client.post(
        f"{API}/bots/{bot_id}/match/run",
        json={"opponent": "random"},
        headers=headers,
    )
    assert response.status_code == 202
    match_id = int(response.json()["matchId"])
    assert match_id > 0

    async with session_factory() as session:
        match = await session.get(BotMatch, match_id)
        assert match is not None
        assert match.finished_at is None


async def test_match_stats_endpoint(
    admin_client, make_client, unique_email, worker_role, redis_client
):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    response = await client.get(f"{API}/bots/stats", headers=headers)
    assert response.status_code == 200
    assert response.json()["elo"] == 1000.0

    response = await client.get(f"{API}/bots/leaderboard", headers=headers)
    assert response.status_code == 200  # S-33: /leaderboard не перехвачен /{bot_id}
    assert isinstance(response.json(), list)

    response = await client.post(
        f"{API}/bots", json={"code": RANDOM_BOT}, headers=headers
    )
    bot_id = int(response.json()["id"])

    from domains.bot_lab.match import run_match

    await run_match(bot_id, "random", redis_client)

    response = await client.get(f"{API}/bots/stats", headers=headers)
    stats = response.json()
    assert stats["wins"] + stats["losses"] + stats["draws"] == 1

    response = await client.get(f"{API}/bots/{bot_id}/matches", headers=headers)
    matches = response.json()
    assert len(matches) == 1
    assert matches[0]["opponent"] == "random"
