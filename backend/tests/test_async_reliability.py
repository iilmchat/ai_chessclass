"""S-73: идемпотентность arq, DLQ failed_jobs и сквозной trace_id."""

import json
import logging
import uuid

import pytest
import sqlalchemy as sa

from core.db import session_factory
from core.jobs import track_job
from core.levels import Level
from core.tracing import trace_context
from domains.bot_lab.models import BotMatch
from domains.observability.models import FailedJob
from llm.base import LLMMessage
from llm.echo import EchoProvider
from llm.gateway import LLMCallContext, llm_generate
from llm.models import LLMCall
from tests.conftest import API, login, register_verified

TRACE = "0123456789abcdef0123456789abcdef"
RANDOM_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)
GOOD_PGN = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"


class FakePool:
    """Запоминает enqueue_job-вызовы; реальный Redis/arq не нужен."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    async def aclose(self) -> None:
        return None


def _install_fake_pool(monkeypatch) -> FakePool:
    pool = FakePool()

    async def fake_create_pool(*args, **kwargs):
        return pool

    monkeypatch.setattr("arq.connections.create_pool", fake_create_pool)
    return pool


async def test_match_request_is_idempotent(make_client, unique_email, monkeypatch):
    """DoD: повторный HTTP-запрос матча не создаёт дубль и job_id стабилен."""
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, user_id = await login(client, unique_email)
    headers = {
        "Authorization": f"Bearer {access}",
        "x-trace-id": TRACE,
    }
    response = await client.post(
        f"{API}/bots", json={"code": RANDOM_BOT}, headers=headers
    )
    bot_id = int(response.json()["id"])
    pool = _install_fake_pool(monkeypatch)

    first = await client.post(
        f"{API}/bots/{bot_id}/match/run",
        json={"opponent": "random"},
        headers=headers,
    )
    second = await client.post(
        f"{API}/bots/{bot_id}/match/run",
        json={"opponent": "random"},
        headers=headers,
    )
    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json()["matchId"] == second.json()["matchId"]
    assert first.headers["x-trace-id"] == TRACE

    async with session_factory() as session:
        count = await session.scalar(
            sa.select(sa.func.count())
            .select_from(BotMatch)
            .where(BotMatch.user_id == user_id)
        )
    assert count == 1

    match_id = int(first.json()["matchId"])
    assert len(pool.calls) == 2
    for args, kwargs in pool.calls:
        assert kwargs["_job_id"] == f"run_match:{match_id}"
        assert args[6] == TRACE


async def test_analyze_game_job_id_and_trace(make_client, unique_email, monkeypatch):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    pool = _install_fake_pool(monkeypatch)

    response = await client.post(
        f"{API}/chess/games/upload",
        json={"pgn": GOOD_PGN},
        headers={
            "Authorization": f"Bearer {access}",
            "x-trace-id": TRACE,
        },
    )
    assert response.status_code == 202, response.text
    game_id = int(response.json()["gameId"])
    assert len(pool.calls) == 1
    args, kwargs = pool.calls[0]
    assert kwargs["_job_id"] == f"analyze_game:{game_id}"
    assert args[4] == TRACE


async def test_failed_job_is_recorded():
    """Упавшая задача попадает в failed_jobs с job_id/trace_id/ошибкой."""

    @track_job("test_dlq")
    async def failing(ctx: dict, trace_id: str | None = None) -> None:
        raise RuntimeError("boom")

    job_id = f"test-dlq-{uuid.uuid4().hex[:8]}"
    with pytest.raises(RuntimeError, match="boom"):
        await failing({"job_id": job_id, "job_try": 2}, trace_id=TRACE)

    async with session_factory() as session:
        row = (
            await session.execute(
                sa.select(FailedJob).where(FailedJob.job_id == job_id)
            )
        ).scalar_one()
    assert row.task == "test_dlq"
    assert row.attempts == 2
    assert row.trace_id == TRACE
    assert row.error_type == "RuntimeError"
    assert "boom" in row.error


def test_json_log_contains_trace_id():
    """DoD: trace_id виден в JSON-логах HTTP/arq (общий formatter)."""
    from core.logging import JsonFormatter

    record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", None, None)
    with trace_context(TRACE):
        payload = json.loads(JsonFormatter().format(record))
    assert payload["trace_id"] == TRACE


async def test_llm_call_stores_trace_id(redis_client):
    async with session_factory() as session:
        with trace_context(TRACE):
            result = await llm_generate(
                session,
                redis_client,
                route="chess_lab.insight",
                level=Level.NOVICE,
                messages=[LLMMessage(role="user", content="FEN: start")],
                ctx=LLMCallContext(),
                provider=EchoProvider(),
            )
        await session.commit()
        assert result.text.startswith("[echo]")

        row = (
            await session.execute(
                sa.select(LLMCall).order_by(LLMCall.id.desc()).limit(1)
            )
        ).scalar_one()
    assert row.trace_id == TRACE
