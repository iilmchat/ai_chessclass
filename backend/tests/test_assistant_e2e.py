"""S-14: сквозные сценарии A/B/D (Design §3.4) с записью llm_calls.

A: сдача Python → вердикт + LLM-комментарий; B: позиция → инсайт;
D: RAG-контекст (knowledge) доходит до промпта. Всё — через gateway с квотами.
"""

import sqlalchemy as sa

from core.db import session_factory
from domains.python_teacher.models import PyAssignment
from llm.models import LLMCall
from tests.conftest import API, login, register_verified

GOOD_CODE = 'def greet(name):\n    return f"Привет, {name}!"\n'


async def _setup_assignment(admin_client) -> int:
    """Задание напрямую в БД (slug test-e2e; чистится по префиксу test-)."""
    async with session_factory() as session:
        session.add(
            PyAssignment(
                slug="test-e2e",
                title="Сквозной сценарий",
                level="novice",
                topic="functions",
                statement="Напиши функцию greet(name), возвращающую приветствие.",
                tests=['assert greet("Аня") == "Привет, Аня!"'],
            )
        )
        await session.commit()
    response = await admin_client.get(f"{API}/py/assignments")
    return next(
        int(item["id"])
        for item in response.json()["items"]
        if item["slug"] == "test-e2e"
    )


async def test_scenario_a_submit_comment_llm_calls(
    admin_client, make_client, unique_email, worker_role
):
    _ = worker_role  # insight/echo-путь совместим с api-ролью; здесь py
    assignment_id = await _setup_assignment(admin_client)
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    # сценарий A: сдача → вердикт + комментарий (LLM по уровню)
    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/submit",
        json={"code": GOOD_CODE},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "passed"
    assert body["feedback"] is not None
    assert body["feedback"]["content"]

    # llm_calls: комментарий записан шлюзом
    async with session_factory() as session:
        rows = (
            await session.execute(
                sa.select(LLMCall).where(
                    LLMCall.user_id == user_id,
                    LLMCall.route == "python_teacher.comment",
                )
            )
        ).scalars().all()
        assert rows, "комментарий должен попасть в llm_calls"
        assert rows[-1].model_used  # echo или слаг облачной модели


async def test_scenario_b_insight_llm_calls(
    admin_client, make_client, unique_email, worker_role
):
    _ = admin_client
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)

    # сценарий B: позиция → факты SF + объяснение
    response = await client.post(
        f"{API}/chess/insight",
        json={"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    assert response.json()["facts"]

    async with session_factory() as session:
        row = (
            await session.execute(
                sa.select(LLMCall)
                .where(
                    LLMCall.user_id == user_id,
                    LLMCall.route == "chess_lab.insight",
                )
                .order_by(LLMCall.id.desc())
                .limit(1)
            )
        ).scalar_one()
        assert row.status in ("ok", "echo")  # dev — echo; прод — ok


async def test_scenario_d_rag_knowledge_reaches_prompt(
    admin_client, make_client, unique_email, worker_role
):
    """RAG-контекст: инжест документа по теме → hint содержит knowledge."""
    from rag.ingest import ingest_document
    from rag.models import RagDocument

    async with session_factory() as session:
        await ingest_document(
            session,
            title_ru="Циклы: подсказки (e2e)",
            source="e2e",
            domain="python",
            kind="explanation",
            text=(
                "Для функции-приветствия достаточно f-строки: "
                "f\"Привет, {name}!\" — return обязателен."
            ),
        )
        await session.commit()

    assignment_id = await _setup_assignment(admin_client)
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)

    # seeded-подсказок нет → сразу LLM (echo), промпт содержит knowledge-блок
    response = await client.post(
        f"{API}/py/assignments/{assignment_id}/hint",
        json={"hintIdx": 0},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    hint = response.json()
    assert hint["source"] == "llm"
    assert "Полезный материал" in hint["content"]  # RAG доходит до LLM

    # чистим e2e-документ базы знаний
    async with session_factory() as session:
        doc = (
            await session.execute(
                sa.select(RagDocument).where(
                    RagDocument.title_ru == "Циклы: подсказки (e2e)"
                )
            )
        ).scalar_one()
        await session.delete(doc)
        await session.commit()
