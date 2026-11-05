"""S-46: observability summary, metrics, costs, alerts, retention API."""

import uuid
from decimal import Decimal

import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from domains.auth.models import User, UserRole
from domains.observability.models import FailedJob
from domains.voice.usage import VoiceUsage
from llm.models import LLMCall
from tests.conftest import API, make_direct_user


async def test_observability_and_retention_api(admin_client, unique_email, monkeypatch):
    await make_direct_user(unique_email, UserRole.STUDENT)
    async with session_factory() as session:
        user = await session.get(
            User,
            int(
                (
                    await session.execute(
                        sa.select(User.id).where(User.email == unique_email)
                    )
                ).scalar_one()
            ),
        )
        assert user is not None
        call = LLMCall(
            user_id=user.id,
            route="test.observability",
            level="novice",
            model_requested="m",
            model_used="echo",
            tokens_in=10,
            tokens_out=5,
            latency_ms=10,
            status="ok",
        )
        session.add(call)
        session.add(
            VoiceUsage(
                user_id=user.id,
                chars=100,
                cost=Decimal("0.5"),
                cached=False,
            )
        )
        await session.commit()
        call_id = call.id

    response = await admin_client.get(f"{API}/admin/observability/summary")
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["db"] is True
    assert summary["redis"] is True
    assert "queues" in summary

    response = await admin_client.get(f"{API}/admin/observability/alerts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    response = await admin_client.get(f"{API}/admin/observability/costs?days=30")
    assert response.status_code == 200, response.text
    costs = response.json()["items"]
    row = next(item for item in costs if item["email"] == unique_email)
    assert row["voiceChars"] == 100
    assert row["llmCostRub"] >= 0

    response = await admin_client.get(f"{API}/admin/observability/costs.csv")
    assert response.status_code == 200
    assert "total_cost_rub" in response.text
    assert unique_email in response.text

    response = await admin_client.post(
        f"{API}/admin/observability/retention/run", json={"dryRun": True}
    )
    assert response.status_code == 200, response.text
    assert all(item["dryRun"] is True for item in response.json())

    response = await admin_client.get(f"{API}/admin/observability/retention/status")
    assert response.status_code == 200
    assert "policies" in response.json()

    response = await admin_client.get("/metrics")
    assert response.status_code == 200
    assert "chessclass_up 1" in response.text
    assert "chessclass_db_up 1" in response.text

    monkeypatch.setattr(settings, "metrics_token", "metrics-secret")
    response = await admin_client.get("/metrics")
    assert response.status_code == 403
    response = await admin_client.get(
        "/metrics", headers={"Authorization": "Bearer metrics-secret"}
    )
    assert response.status_code == 200

    async with session_factory() as session:
        await session.execute(sa.delete(LLMCall).where(LLMCall.id == call_id))
        await session.commit()


async def test_failed_jobs_list_retry_and_alert(admin_client, monkeypatch):
    job_id = f"test-dlq-{uuid.uuid4().hex[:10]}"
    async with session_factory() as session:
        row = FailedJob(
            job_id=job_id,
            task="heartbeat",
            args={"args": [], "kwargs": {}},
            error_type="RuntimeError",
            error="boom",
            attempts=2,
            trace_id="a" * 32,
            status="failed",
        )
        session.add(row)
        await session.commit()
        row_id = row.id

    monkeypatch.setattr(settings, "obs_failed_jobs_alert_threshold", 0)
    alerts = await admin_client.get(f"{API}/admin/observability/alerts")
    assert alerts.status_code == 200
    assert any(
        item["code"] == "failed_jobs_growth" for item in alerts.json()
    )

    response = await admin_client.get(
        f"{API}/admin/observability/failed-jobs?status=failed"
    )
    assert response.status_code == 200, response.text
    assert any(item["id"] == str(row_id) for item in response.json())

    class FakePool:
        def __init__(self):
            self.calls: list[tuple[tuple, dict]] = []

        async def enqueue_job(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return object()

        async def aclose(self):
            return None

    pool = FakePool()

    async def fake_create_pool(*args, **kwargs):
        return pool

    monkeypatch.setattr("arq.connections.create_pool", fake_create_pool)
    response = await admin_client.post(
        f"{API}/admin/observability/failed-jobs/{row_id}/retry"
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "retried"
    assert pool.calls and pool.calls[0][0][0] == "heartbeat"

    response = await admin_client.get(
        f"{API}/admin/observability/failed-jobs?status=retried"
    )
    assert response.status_code == 200
    assert any(item["id"] == str(row_id) for item in response.json())

    async with session_factory() as session:
        await session.execute(sa.delete(FailedJob).where(FailedJob.id == row_id))
        await session.commit()
