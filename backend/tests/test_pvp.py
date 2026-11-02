"""S-51: PvP-комнаты, quick-match, отдельный рейтинг, жалобы."""

import sqlalchemy as sa

from core.db import session_factory
from domains.auth.models import User
from domains.pvp import service as pvp_svc
from domains.pvp.models import PvpRating, PvpRoom
from domains.tournaments.service import run_tournament_job
from tests.conftest import API, login, register_verified

RANDOM_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)


async def _student(make_client, email):
    client = await make_client()
    await register_verified(client, email)
    _c, access, user_id = await login(client, email)
    headers = {"Authorization": f"Bearer {access}"}
    response = await client.post(
        f"{API}/bots",
        json={"code": RANDOM_BOT, "entry": "choose_move"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return client, headers, user_id, int(response.json()["id"])


async def test_pvp_room_start_and_rating(make_client, unique_email, admin_client):
    host_client, host_headers, host_id, host_bot = await _student(
        make_client, unique_email
    )
    guest_client, guest_headers, guest_id, guest_bot = await _student(
        make_client, f"g-{unique_email}"
    )

    response = await host_client.post(
        f"{API}/pvp/rooms",
        headers=host_headers,
        json={"botVersionId": host_bot},
    )
    assert response.status_code == 201, response.text
    room = response.json()
    assert room["status"] == "waiting"

    response = await guest_client.post(
        f"{API}/pvp/rooms/join",
        headers=guest_headers,
        json={"code": room["code"], "botVersionId": guest_bot},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"

    async with session_factory() as session:
        host = await session.get(User, host_id)
        assert host is not None
        started, tournament = await pvp_svc.start_room(
            session, host, int(room["id"])
        )
        await session.commit()
        assert started.status == "running"

    async def fake_match(_a, _b):
        return "a", 1, 5, []

    async with session_factory() as session:
        done = await run_tournament_job(
            tournament.id, session=session, match_runner=fake_match
        )
        assert done.status == "done"
        room_row = await session.get(PvpRoom, int(room["id"]))
        assert room_row is not None and room_row.status == "done"
        host_rating = await session.get(PvpRating, host_id)
        guest_rating = await session.get(PvpRating, guest_id)
        assert host_rating is not None and guest_rating is not None
        assert float(host_rating.elo) > 1000 > float(guest_rating.elo)

    response = await guest_client.get(
        f"{API}/pvp/leaderboard", headers=guest_headers
    )
    assert response.status_code == 200
    assert any(row["userId"] == str(host_id) for row in response.json())

    response = await guest_client.post(
        f"{API}/pvp/rooms/{room['id']}/complaints",
        headers=guest_headers,
        json={"reason": "Проверьте честность матча"},
    )
    assert response.status_code == 200, response.text

    response = await admin_client.get(f"{API}/admin/pvp/complaints")
    assert response.status_code == 200
    assert any(row["reason"] == "Проверьте честность матча" for row in response.json())


async def test_pvp_quick_match(make_client, unique_email):
    host_client, host_headers, _host_id, host_bot = await _student(
        make_client, unique_email
    )
    guest_client, guest_headers, _guest_id, guest_bot = await _student(
        make_client, f"q-{unique_email}"
    )
    response = await host_client.post(
        f"{API}/pvp/rooms", headers=host_headers, json={"botVersionId": host_bot}
    )
    assert response.status_code == 201

    response = await guest_client.post(
        f"{API}/pvp/quick-match",
        headers=guest_headers,
        json={"botVersionId": guest_bot},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched"] is True
    assert body["room"]["status"] == "ready"

    async with session_factory() as session:
        assert (
            await session.execute(
                sa.select(PvpRoom).where(PvpRoom.status == "ready")
            )
        ).scalar_one_or_none() is not None
