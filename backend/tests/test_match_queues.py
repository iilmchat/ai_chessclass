"""S-37: per-queue лимиты, лимит активных матчей, admin-метрики."""

from tests.conftest import API, login, register_verified

RANDOM_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)


def test_queue_mapping_and_limits():
    from domains.bot_lab.queues import (
        MATCH_QUEUE_LIMITS,
        MATCH_QUEUES,
        MAX_ACTIVE_MATCHES,
        queue_for_opponent,
        queue_kind,
    )

    assert queue_kind("random") == "random"
    assert queue_kind("greedy") == "greedy"
    assert queue_kind("minimax2") == "minimax"
    assert queue_kind("stockfish-1400") == "sf"
    assert queue_for_opponent("minimax2") == "arq:matches:minimax"
    assert set(MATCH_QUEUES) == {"random", "greedy", "minimax", "sf"}
    assert sum(MATCH_QUEUE_LIMITS.values()) == MAX_ACTIVE_MATCHES == 5


async def test_per_user_match_limit(make_client, unique_email, monkeypatch):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    class FakePool:
        async def enqueue_job(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def aclose(self):
            return None

    async def fake_create_pool(*args, **kwargs):
        return FakePool()

    monkeypatch.setattr("arq.connections.create_pool", fake_create_pool)

    async def new_bot() -> int:
        response = await client.post(
            f"{API}/bots", json={"code": RANDOM_BOT}, headers=headers
        )
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    # S-73: одинаковый bot+opponent дедуплицируется, поэтому лимит
    # проверяем на пяти разных ботах (активные матчи одного пользователя).
    for _ in range(5):
        bot_id = await new_bot()
        response = await client.post(
            f"{API}/bots/{bot_id}/match/run",
            json={"opponent": "random"},
            headers=headers,
        )
        assert response.status_code == 202, response.text

    bot_id = await new_bot()
    response = await client.post(
        f"{API}/bots/{bot_id}/match/run",
        json={"opponent": "random"},
        headers=headers,
    )
    assert response.status_code == 429
    assert response.json()["code"] == "match_limit"


async def test_match_metrics_endpoint(admin_client):
    response = await admin_client.get(f"{API}/admin/matches/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["hours"] == 24
    assert isinstance(body["byOpponent"], dict)
    assert body["refused"] >= 0
    assert len(body["queues"]) == 4
    assert sum(item["limit"] for item in body["queues"]) == 5
