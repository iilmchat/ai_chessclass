"""S-45: турнир 8 ботов без LLM + экспорт CSV/xAPI."""

from core.db import session_factory
from domains.auth.models import User, UserRole
from domains.bot_lab.models import BotVersion
from domains.tournaments.service import run_tournament
from tests.conftest import API, login, make_direct_user

BOT_CODE = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)


async def _fake_match(bot_a, bot_b):
    # Детерминированный турнирный матч без песочницы/LLM.
    return ("a" if bot_a.id < bot_b.id else "b", 10, 100)


async def test_eight_bot_bracket_and_exports(
    admin_client, make_client, unique_email
):
    _ = admin_client
    client = await make_client()
    await make_direct_user(f"t-{unique_email}", UserRole.TEACHER)
    _c, access, teacher_id = await login(client, f"t-{unique_email}")
    headers = {"Authorization": f"Bearer {access}"}

    async with session_factory() as session:
        teacher = await session.get(User, teacher_id)
        assert teacher is not None
        bots: list[BotVersion] = []
        for index in range(8):
            bot = BotVersion(
                user_id=teacher.id,
                version_no=index + 1,
                code=BOT_CODE,
                entry="choose_move",
            )
            session.add(bot)
            bots.append(bot)
        await session.flush()
        tournament = await run_tournament(
            session,
            teacher,
            name="Турнир 8 ботов",
            format="bracket",
            bot_ids=[bot.id for bot in bots],
            match_runner=_fake_match,
        )
        await session.commit()
        tournament_id = tournament.id

    response = await client.get(f"{API}/tournaments", headers=headers)
    assert response.status_code == 200, response.text
    assert any(item["id"] == str(tournament_id) for item in response.json())

    response = await client.get(
        f"{API}/tournaments/{tournament_id}", headers=headers
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["status"] == "done"
    assert len(detail["participants"]) == 8
    assert len(detail["matches"]) == 7  # bracket: 4 + 2 + 1
    assert detail["participants"][0]["rank"] == 1
    assert detail["participants"][0]["points"] > 0

    response = await client.get(
        f"{API}/admin/tournaments/{tournament_id}/export.csv", headers=headers
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "rank" in response.text and "bot_version_id" in response.text

    # LMS-экспорт (CSV + xAPI) доступен teacher
    response = await client.get(f"{API}/admin/export/skills.csv", headers=headers)
    assert response.status_code == 200
    assert "skill_slug" in response.text
    response = await client.get(f"{API}/admin/export/xapi", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert "statements" in payload
    assert isinstance(payload["statements"], list)
    if payload["statements"]:
        statement = payload["statements"][0]
        assert statement["actor"]["mbox"].startswith("mailto:")
        assert statement["verb"]["id"].startswith("http://adlnet.gov/expapi/verbs/")
        assert statement["object"]["id"].startswith("https://chessclass.local/")


async def test_tournament_requires_teacher(admin_client, make_client, unique_email):
    _ = admin_client
    client = await make_client()
    await make_direct_user(unique_email, UserRole.STUDENT)
    _c, access, _uid = await login(client, unique_email)
    response = await client.post(
        f"{API}/admin/tournaments",
        json={"name": "Нельзя", "format": "bracket", "botVersionIds": [1, 2]},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 403
