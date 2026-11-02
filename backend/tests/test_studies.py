"""S-43: генерация этюдов, ревью, публикация и попытки решения."""

import chess

from core.db import session_factory
from domains.auth.models import User, UserRole
from domains.studies.service import generate_study
from tests.conftest import API, login, make_direct_user

CONDITION = "Найди лучший ход за сторону, которая ходит."


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
    return CONDITION


async def _teacher(client, email: str):
    await make_direct_user(email, UserRole.TEACHER)
    _client, access, user_id = await login(client, email)
    return {"Authorization": f"Bearer {access}"}, user_id


async def test_five_studies_reviewed_and_solved(admin_client, make_client, unique_email):
    _ = admin_client
    client = await make_client()
    teacher_headers, teacher_id = await _teacher(client, f"t-{unique_email}")
    student_email = f"s-{unique_email}"
    await make_direct_user(student_email, UserRole.STUDENT)
    _client, student_access, _student_id = await login(client, student_email)
    student_headers = {"Authorization": f"Bearer {student_access}"}

    study_ids: list[int] = []
    solutions: dict[int, str] = {}
    async with session_factory() as session:
        teacher = await session.get(User, teacher_id)
        assert teacher is not None
        for index in range(5):
            study = await generate_study(
                session,
                None,
                teacher,
                candidate_index=index,
                analyze=_fake_analyze,
                generate_text=_fake_text,
            )
            assert study.status.value == "draft"
            assert study.condition_text == CONDITION
            assert study.solution_uci in {
                move.uci() for move in chess.Board(study.fen).legal_moves
            }
            study_ids.append(study.id)
            solutions[study.id] = study.solution_uci
        await session.commit()

    for study_id in study_ids:
        response = await client.post(
            f"{API}/admin/studies/{study_id}/submit", headers=teacher_headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "review"
        response = await client.post(
            f"{API}/admin/studies/{study_id}/review",
            json={"decision": "approve", "note": "ок"},
            headers=teacher_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "published"

    response = await client.get(f"{API}/studies", headers=student_headers)
    assert response.status_code == 200, response.text
    public_ids = {item["id"] for item in response.json()["items"]}
    assert {str(study_id) for study_id in study_ids} <= public_ids
    assert all("solutionUci" not in item for item in response.json()["items"])

    for study_id in study_ids:
        response = await client.post(
            f"{API}/studies/{study_id}/attempt",
            json={"moveUci": solutions[study_id]},
            headers=student_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["correct"] is True
        response = await client.post(
            f"{API}/studies/{study_id}/attempt",
            json={"moveUci": "a1a2"},
            headers=student_headers,
        )
        # либо неверный ход, либо нелегальный — оба варианта не «correct»
        assert response.status_code in (200, 422)
        if response.status_code == 200:
            assert response.json()["correct"] is False

    # брак: черновик → review → reject; в публичной ленте не появляется
    async with session_factory() as session:
        teacher = await session.get(User, teacher_id)
        assert teacher is not None
        rejected = await generate_study(
            session,
            None,
            teacher,
            candidate_index=0,
            analyze=_fake_analyze,
            generate_text=_fake_text,
        )
        await session.commit()
        rejected_id = rejected.id
    response = await client.post(
        f"{API}/admin/studies/{rejected_id}/submit", headers=teacher_headers
    )
    assert response.status_code == 200
    response = await client.post(
        f"{API}/admin/studies/{rejected_id}/review",
        json={"decision": "reject", "note": "дубль"},
        headers=teacher_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    response = await client.get(f"{API}/studies/{rejected_id}", headers=student_headers)
    assert response.status_code == 404
    response = await client.get(f"{API}/studies", headers=student_headers)
    assert str(rejected_id) not in {item["id"] for item in response.json()["items"]}
