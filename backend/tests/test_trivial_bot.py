"""S-21: trivial_bot — тривиальный бот получает флаг, валидный не трогается."""

import sqlalchemy as sa

from core.db import session_factory
from domains.anticheat.models import AnticheatFlag
from tests.conftest import API, login, register_verified

TRIVIAL_BOT = "def choose_move(position):\n    return 'e2e4'\n"
VALID_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)


async def test_trivial_bot_gets_flag(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)

    response = await client.post(
        f"{API}/bots", json={"code": TRIVIAL_BOT}, headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 201

    async with session_factory() as session:
        flag = (
            await session.execute(
                sa.select(AnticheatFlag).where(
                    AnticheatFlag.user_id == user_id,
                    AnticheatFlag.kind == "trivial_bot",
                )
            )
        ).scalar_one()
        assert flag.status.value == "new"
        assert flag.domain.value == "bot"
        evidence = flag.evidence
        assert "short_code" in evidence["reasons"]
        assert "hardcoded_moves" in evidence["reasons"]
        assert evidence["codeLines"] <= 2


async def test_valid_bot_not_flagged(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)

    response = await client.post(
        f"{API}/bots", json={"code": VALID_BOT}, headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 201

    async with session_factory() as session:
        flag = (
            await session.execute(
                sa.select(AnticheatFlag).where(
                    AnticheatFlag.user_id == user_id,
                    AnticheatFlag.kind == "trivial_bot",
                )
            )
        ).scalar_one_or_none()
        assert flag is None
