"""S-53: batch-генерация без дублей и многоходовый solver."""

import chess

from core.db import session_factory
from domains.auth.models import User, UserRole
from domains.studies.models import ChessStudy, StudyStatus
from domains.studies.service import generate_batch, generator_metrics
from tests.conftest import API, login, make_direct_user, register_verified


async def _fake_analyze(fen: str, _level):
    board = chess.Board(fen)
    move = next(iter(board.legal_moves)).uci()
    return [
        {
            "multipv": 1,
            "depth": 10,
            "score_cp": 80,
            "mate": None,
            "move_uci": move,
            "pv": [move],
        }
    ]


async def _fake_text() -> str:
    return "Найдите лучший ход."


async def test_study_batch_unique_and_metrics(unique_email):
    teacher_id = await make_direct_user(
        f"t-{unique_email}", UserRole.TEACHER
    )
    async with session_factory() as session:
        teacher = await session.get(User, teacher_id)
        assert teacher is not None
        result = await generate_batch(
            session,
            None,
            teacher,
            count=6,
            analyze=_fake_analyze,
            generate_text=_fake_text,
        )
        await session.commit()
        assert len(result["created"]) == 6
        assert result["skipped"] == 0
        assert result["uniqueFens"] == 6
        fens = [study.fen for study in result["created"]]
        assert len(set(fens)) == 6
        metrics = await generator_metrics(session)
        assert metrics["generated"] >= 6
        assert metrics["duplicateFens"] >= 0
        assert metrics["defectRate"] <= 0.2


async def test_multi_move_attempt(make_client, unique_email):
    teacher_id = await make_direct_user(
        f"t-{unique_email}", UserRole.TEACHER
    )
    async with session_factory() as session:
        teacher = await session.get(User, teacher_id)
        assert teacher is not None
        study = ChessStudy(
            title="Мат в два",
            fen=chess.STARTING_FEN,
            condition_text="Найдите линию",
            theme="opening",
            difficulty="novice",
            solution_uci="e2e4",
            solution_line=["e2e4", "e7e5"],
            status=StudyStatus.PUBLISHED,
            source="manual",
            created_by=teacher_id,
        )
        session.add(study)
        await session.commit()
        study_id = study.id

    student_email = f"s-{unique_email}"
    await make_direct_user(student_email, UserRole.STUDENT)
    client = await make_client()
    await register_verified(client, f"x-{unique_email}")
    _c, access, _uid = await login(client, f"x-{unique_email}")
    headers = {"Authorization": f"Bearer {access}"}
    # публичный пользователь должен видеть published-этюд
    response = await client.post(
        f"{API}/studies/{study_id}/attempt-line",
        headers=headers,
        json={"moves": ["e2e4", "e7e5"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["correct"] is True
    assert response.json()["nextUci"] is None

    response = await client.post(
        f"{API}/studies/{study_id}/attempt-line",
        headers=headers,
        json={"moves": ["e2e4", "e7e6"]},
    )
    assert response.status_code == 200
    assert response.json()["correct"] is False
    assert response.json()["failedPly"] == 1
