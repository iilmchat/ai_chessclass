"""S-46: observability summary, metrics, costs, alerts, retention API."""

import gzip
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from core.http_metrics import reset_http_metrics
from domains.auth.models import User, UserRole
from domains.notifications.models import EmailOutbox
from domains.observability.models import FailedJob
from domains.retention.models import LegalHold
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


async def test_http_metrics_histogram_for_p95(admin_client):
    reset_http_metrics()
    _ = await admin_client.get(f"{API}/healthz")
    response = await admin_client.get("/metrics")
    assert response.status_code == 200
    assert "chessclass_http_requests_total" in response.text
    assert "chessclass_http_request_duration_seconds_bucket" in response.text
    assert "chessclass_http_request_duration_seconds_count" in response.text


async def test_backup_status_metrics(admin_client, tmp_path, monkeypatch):
    """S-93: gauges последнего offsite-бэкапа/restore из status JSON."""
    status = tmp_path / "backup-status.json"
    status.write_text(
        '{"last_success_timestamp": 1700000000, "last_restore_ok": false}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "backup_status_file", str(status))
    response = await admin_client.get("/metrics")
    assert response.status_code == 200
    assert "chessclass_backup_last_success_timestamp_seconds 1700000000" in (
        response.text
    )
    assert "chessclass_backup_restore_ok 0" in response.text


async def test_email_outbox_and_retention_metrics(admin_client, tmp_path, monkeypatch):
    """S-88: gauges stuck email_outbox и возраста retention-архива в /metrics."""
    kind = "test-s88-metrics"
    now = datetime.now(UTC)
    async with session_factory() as session:
        await session.execute(
            sa.delete(EmailOutbox).where(EmailOutbox.kind == kind)
        )
        session.add_all(
            [
                # pending: ждёт доставки 2 часа
                EmailOutbox(
                    kind=kind,
                    recipient="parent@example.com",
                    subject="pending",
                    body="pending-body",
                    status="pending",
                    attempts=0,
                    next_attempt_at=now - timedelta(hours=2),
                    created_at=now - timedelta(hours=2),
                ),
                # parked failed: исчерпал попытки — входит в pending_total
                EmailOutbox(
                    kind=kind,
                    recipient="parent@example.com",
                    subject="parked",
                    body="parked-body",
                    status="failed",
                    attempts=settings.email_outbox_max_attempts,
                    last_error="smtp down",
                    next_attempt_at=now + timedelta(days=365),
                    created_at=now - timedelta(days=3),
                ),
                # retryable failed: ещё не доставлен — влияет на возраст
                EmailOutbox(
                    kind=kind,
                    recipient="parent@example.com",
                    subject="retry",
                    body="retry-body",
                    status="failed",
                    attempts=settings.email_outbox_max_attempts - 1,
                    last_error="temporary",
                    next_attempt_at=now + timedelta(minutes=5),
                    created_at=now - timedelta(hours=4),
                ),
                # sent: не должен попадать ни в pending_total, ни в возраст
                EmailOutbox(
                    kind=kind,
                    recipient="parent@example.com",
                    subject="sent",
                    body="sent-body",
                    status="sent",
                    attempts=1,
                    next_attempt_at=now - timedelta(days=5),
                    created_at=now - timedelta(days=5),
                    sent_at=now - timedelta(days=5),
                ),
            ]
        )
        await session.commit()

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    archive = archive_dir / "email_outbox-20260101T000000Z.jsonl.gz"
    with gzip.open(archive, "wt", encoding="utf-8") as handle:
        handle.write('{"id": 1}\n')
    archive_ts = time.time() - 10 * 24 * 3600
    os.utime(archive, (archive_ts, archive_ts))
    monkeypatch.setattr(settings, "retention_archive_dir", str(archive_dir))

    try:
        response = await admin_client.get("/metrics")
        assert response.status_code == 200, response.text
        text = response.text
        for name in (
            "chessclass_email_outbox_pending_total",
            "chessclass_email_outbox_oldest_pending_age_seconds",
            "chessclass_retention_archive_age_seconds",
            "chessclass_failed_jobs",
        ):
            assert name in text, name

        def metric_value(name: str) -> float:
            line = next(
                row for row in text.splitlines() if row.startswith(f"{name} ")
            )
            return float(line.split()[-1])

        async with session_factory() as session:
            expected_pending = int(
                await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(EmailOutbox)
                    .where(
                        sa.or_(
                            EmailOutbox.status == "pending",
                            sa.and_(
                                EmailOutbox.status == "failed",
                                EmailOutbox.attempts
                                >= settings.email_outbox_max_attempts,
                            ),
                        )
                    )
                )
                or 0
            )
        assert metric_value("chessclass_email_outbox_pending_total") == expected_pending
        # Самое старое недоставленное письмо — retryable failed (4 часа).
        assert metric_value(
            "chessclass_email_outbox_oldest_pending_age_seconds"
        ) >= 4 * 3600 - 60
        archive_age = metric_value("chessclass_retention_archive_age_seconds")
        assert 10 * 86400 - 120 <= archive_age <= 10 * 86400 + 120
    finally:
        async with session_factory() as session:
            await session.execute(
                sa.delete(EmailOutbox).where(EmailOutbox.kind == kind)
            )
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


async def test_legal_hold_and_body_scrub_metrics(
    admin_client, unique_email, monkeypatch
):
    """S-98: gauges legal hold и email body pending scrub."""
    user_id = await make_direct_user(unique_email)
    kind = "test-s98-metrics"
    old = datetime.now(UTC) - timedelta(days=60)
    async with session_factory() as session:
        await session.execute(sa.delete(EmailOutbox).where(EmailOutbox.kind == kind))
        session.add(
            EmailOutbox(
                kind=kind,
                recipient=unique_email,
                subject="old",
                body="secret",
                status="sent",
                attempts=1,
                next_attempt_at=old,
                created_at=old,
                sent_at=old,
            )
        )
        await session.commit()

    response = await admin_client.post(
        f"{API}/admin/legal-holds",
        json={
            "subjectType": "user",
            "subjectId": str(user_id),
            "reason": "metrics-test",
        },
    )
    assert response.status_code == 201, response.text
    hold_id = int(response.json()["id"])
    try:
        response = await admin_client.get("/metrics")
        assert response.status_code == 200
        text = response.text
        assert "chessclass_legal_holds_active_total" in text
        assert "chessclass_email_outbox_body_pending_scrub_total" in text
        assert "chessclass_retention_last_success_timestamp_seconds" in text
        legal = next(
            line for line in text.splitlines()
            if line.startswith("chessclass_legal_holds_active_total ")
        )
        scrub = next(
            line for line in text.splitlines()
            if line.startswith(
                "chessclass_email_outbox_body_pending_scrub_total "
            )
        )
        assert int(legal.rsplit(" ", 1)[1]) >= 1
        assert int(scrub.rsplit(" ", 1)[1]) >= 1
    finally:
        await admin_client.delete(f"{API}/admin/legal-holds/{hold_id}")
        async with session_factory() as session:
            await session.execute(
                sa.delete(EmailOutbox).where(EmailOutbox.kind == kind)
            )
            await session.execute(
                sa.delete(LegalHold).where(LegalHold.subject_id == str(user_id))
            )
            await session.commit()
