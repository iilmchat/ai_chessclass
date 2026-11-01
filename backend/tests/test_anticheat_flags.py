"""S-22: античит — лента флагов, review, engine_likeliness (real SF)."""

from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from domains.anticheat.likeliness import check_engine_likeliness, sf_match_rate
from domains.anticheat.models import AnticheatFlag, FlagDomain, FlagKind
from tests.conftest import API, login, register_verified

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


async def test_flags_review_flow(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)

    async with session_factory() as session:
        session.add(
            AnticheatFlag(
                user_id=user_id,
                kind=FlagKind.LOW_EFFORT,
                domain=FlagDomain.PYTHON,
                confidence=Decimal("0.60"),
                evidence={"reasons": ["tiny_code"]},
            )
        )
        await session.commit()

    response = await admin_client.get(
        f"{API}/admin/anticheat/flags", params={"status": "new"}
    )
    assert response.status_code == 200
    flags = response.json()
    assert len(flags) >= 1
    flag_id = flags[0]["id"]

    _c, student_access, _uid = await login(client, unique_email)
    response = await client.get(
        f"{API}/admin/anticheat/flags",
        headers={"Authorization": f"Bearer {student_access}"},
    )
    assert response.status_code == 403

    response = await admin_client.post(
        f"{API}/admin/anticheat/flags/{flag_id}/review",
        json={"status": "false_positive", "note": "валидный минимальный бот"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "false_positive"

    response = await admin_client.get(
        f"{API}/admin/anticheat/flags", params={"status": "false_positive"}
    )
    assert any(f["id"] == flag_id for f in response.json())


async def test_engine_likeliness_real_sf(
    admin_client, make_client, unique_email, worker_role, redis_client
):
    if not Path(settings.stockfish_path).exists():
        pytest.skip("Stockfish не установлен")

    from engine.service import EngineService

    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)

    fens = [
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2",
        "rnbqkbnr/ppp2ppp/8/3pp3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3",
    ]
    samples = []
    async with EngineService() as engine:
        for fen in fens:
            lines = await engine.analyze(fen, "analysis", interactive=False)
            samples.append({"fenBefore": fen, "playedUci": lines[0].move_uci})

        rate = await sf_match_rate(engine, samples)
    assert rate["samples"] == 3
    assert rate["top1Rate"] == 1.0  # ходы = топ-1 SF → 100 % совпадение

    async with session_factory() as session:
        await check_engine_likeliness(
            session, redis_client, user_id, bot_version_id=1, match_id=1,
            samples=samples,
        )
        await session.commit()
        flag = (
            await session.execute(
                sa.select(AnticheatFlag).where(
                    AnticheatFlag.user_id == user_id,
                    AnticheatFlag.kind == "engine_likeliness",
                )
            )
        ).scalar_one()
        assert float(flag.confidence) == 0.75
        assert flag.evidence["top1Rate"] == 1.0
