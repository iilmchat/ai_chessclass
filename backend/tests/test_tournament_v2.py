"""S-48: async-турнир, replay, идемпотентность и отмена."""

from sqlalchemy import select

from core.db import session_factory
from domains.auth.models import User, UserRole
from domains.bot_lab.models import BotVersion
from domains.tournaments.service import (
    cancel_tournament,
    create_tournament,
    get_replay,
    get_tournament,
    run_tournament_job,
)
from tests.conftest import API, make_direct_user

BOT_CODE = "def choose_move(position):\n    return next(iter(position.legal_moves))\n"


async def _fake_match(bot_a, bot_b):
    return (
        "a" if bot_a.id < bot_b.id else "b",
        4,
        25,
        [
            {
                "bot_version_id": bot_a.id,
                "ply": 1,
                "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "uci": "e2e4",
                "agent": "a",
                "think_ms": 5,
                "sf_sample": True,
            },
            {
                "bot_version_id": bot_b.id,
                "ply": 2,
                "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                "uci": "e7e5",
                "agent": "b",
                "think_ms": 5,
                "sf_sample": True,
            },
        ],
    )


async def _teacher_with_bots(email: str, count: int):
    await make_direct_user(email, UserRole.TEACHER)
    async with session_factory() as session:
        teacher = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        bots = []
        for index in range(count):
            bot = BotVersion(
                user_id=teacher.id,
                version_no=index + 1,
                code=BOT_CODE,
                entry="choose_move",
            )
            session.add(bot)
            bots.append(bot)
        await session.flush()
        ids = [bot.id for bot in bots]
        await session.commit()
        return teacher, ids


async def test_async_bracket_replay_and_idempotency(
    admin_client, unique_email
):
    _ = admin_client
    teacher, bot_ids = await _teacher_with_bots(unique_email, 8)
    async with session_factory() as session:
        teacher = await session.get(User, teacher.id)
        assert teacher is not None
        tournament = await create_tournament(
            session,
            teacher,
            name="Async bracket",
            format="bracket",
            bot_ids=bot_ids,
        )
        await session.commit()
        tournament_id = tournament.id
        assert tournament.status == "queued"
        assert tournament.total_matches == 7

    result = await run_tournament_job(
        tournament_id, None, match_runner=_fake_match
    )
    assert result.status == "done"
    assert result.progress == 7
    assert result.finished_at is not None

    async with session_factory() as session:
        tournament, participants, matches = await get_tournament(
            session, tournament_id
        )
        assert tournament.status == "done"
        assert len(participants) == 8
        assert len(matches) == 7
        assert all(p.rank is not None for p in participants)
        assert matches[0].moves_count == 4
        replay_match, moves = await get_replay(
            session, tournament_id, matches[0].id
        )
        assert replay_match.id == matches[0].id
        assert len(moves) == 2
        assert moves[0].sf_sample is True

    response = await admin_client.get(
        f"{API}/tournaments/{tournament_id}/events"
    )
    assert response.status_code == 200
    assert "event: status" in response.text
    assert "done" in response.text

    # повторный запуск (рестарт/recovery) не дублирует матчи
    again = await run_tournament_job(
        tournament_id, None, match_runner=_fake_match
    )
    assert again.status == "done"
    async with session_factory() as session:
        _t, _p, matches_again = await get_tournament(
            session, tournament_id
        )
        assert len(matches_again) == 7


async def test_cancel_queued_tournament(admin_client, unique_email):
    _ = admin_client
    teacher, bot_ids = await _teacher_with_bots(unique_email, 2)
    async with session_factory() as session:
        teacher = await session.get(User, teacher.id)
        assert teacher is not None
        tournament = await create_tournament(
            session,
            teacher,
            name="Cancel me",
            format="bracket",
            bot_ids=bot_ids,
        )
        await session.commit()
        tid = tournament.id

    async with session_factory() as session:
        cancelled = await cancel_tournament(session, tid)
        assert cancelled.status == "cancelled"
    result = await run_tournament_job(tid, None, match_runner=_fake_match)
    assert result.status == "cancelled"
