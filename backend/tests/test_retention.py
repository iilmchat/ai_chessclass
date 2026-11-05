"""S-46: retention — архив и удаление старых журналов/кэша."""

from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from domains.audit.models import AuditLog
from domains.auth.models import User, UserRole
from domains.observability.models import FailedJob
from domains.retention.service import last_run, retention_counts, run_retention
from domains.studies.models import ChessStudy, StudyStatus
from domains.voice.models import VoiceAudio
from domains.voice.usage import VoiceUsage
from llm.models import LLMCall
from tests.conftest import make_direct_user


async def test_retention_archives_and_keeps_published(
    unique_email, tmp_path, monkeypatch
):
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
        old = datetime(2025, 1, 1, tzinfo=UTC)
        now = datetime(2026, 1, 10, tzinfo=UTC)
        voice_file = tmp_path / "old.mp3"
        voice_file.write_bytes(b"old-audio")
        session.add_all(
            [
                AuditLog(
                    actor_id=user.id,
                    actor_email=user.email,
                    actor_role="student",
                    action="test.old",
                    source="api",
                    created_at=old,
                ),
                LLMCall(
                    user_id=user.id,
                    route="test.old",
                    level="novice",
                    model_requested="m",
                    model_used="echo",
                    tokens_in=1,
                    tokens_out=1,
                    latency_ms=1,
                    status="ok",
                    created_at=old,
                ),
                VoiceAudio(
                    text_hash=f"hash-{unique_email}",
                    voice_id="v",
                    model_id="m",
                    path=str(voice_file),
                    chars=10,
                    cost=Decimal("0.01"),
                    created_at=old,
                ),
                VoiceUsage(
                    user_id=user.id,
                    chars=10,
                    cost=Decimal("0.01"),
                    cached=False,
                    created_at=old,
                ),
                ChessStudy(
                    title="old draft",
                    fen="8/8/8/4k3/8/4K3/4P3/8 w - - 0 1",
                    condition_text="old",
                    solution_uci="e2e4",
                    status=StudyStatus.DRAFT,
                    created_by=user.id,
                    created_at=old,
                ),
                FailedJob(
                    job_id=f"test-retention-{unique_email}",
                    task="heartbeat",
                    args={"args": [], "kwargs": {}},
                    error_type="RuntimeError",
                    error="old failure",
                    attempts=1,
                    status="failed",
                    failed_at=old,
                ),
                ChessStudy(
                    title="old published",
                    fen="8/8/8/4k3/8/4K3/4P3/8 w - - 0 1",
                    condition_text="keep",
                    solution_uci="e2e4",
                    status=StudyStatus.PUBLISHED,
                    created_by=user.id,
                    created_at=old,
                ),
            ]
        )
        await session.flush()
        published = (
            await session.execute(
                sa.select(ChessStudy).where(ChessStudy.title == "old published")
            )
        ).scalar_one()
        published_id = published.id
        await session.commit()

    monkeypatch.setattr(settings, "retention_archive_dir", str(tmp_path / "archive"))
    monkeypatch.setattr(settings, "audit_retention_days", 30)
    monkeypatch.setattr(settings, "llm_calls_retention_days", 30)
    monkeypatch.setattr(settings, "voice_retention_days", 30)
    monkeypatch.setattr(settings, "studies_retention_days", 30)
    monkeypatch.setattr(settings, "failed_jobs_retention_days", 30)

    async with session_factory() as session:
        counts = await retention_counts(session, now=now)
        assert any(item["policy"] == "audit_logs" and item["rows"] >= 1 for item in counts)
        results = await run_retention(session, now=now)
        await session.commit()
        deleted = {item.policy: item.deleted for item in results}
        assert deleted["audit_logs"] >= 1
        assert deleted["llm_calls"] >= 1
        assert deleted["failed_jobs"] >= 1
        assert deleted["voice_audio"] >= 1
        assert deleted["voice_usage"] >= 1
        assert deleted["chess_studies"] == 1
        assert not voice_file.exists()
        assert await last_run(session) is not None
        published_row = await session.get(ChessStudy, published_id)
        assert published_row is not None
        assert published_row.status is StudyStatus.PUBLISHED
        assert list((tmp_path / "archive").glob("*.jsonl.gz"))

    # dry-run: строка остаётся, файл архива не создаётся
    async with session_factory() as session:
        session.add(
            AuditLog(action="test.dry", source="api", created_at=datetime(2025, 1, 1, tzinfo=UTC))
        )
        await session.commit()
    before = set((tmp_path / "archive").glob("*"))
    async with session_factory() as session:
        results = await run_retention(session, now=now, dry_run=True)
        await session.commit()
        assert any(item.policy == "audit_logs" and item.dry_run for item in results)
        row = (
            await session.execute(
                sa.select(AuditLog).where(AuditLog.action == "test.dry")
            )
        ).scalar_one()
        assert row is not None
    assert set((tmp_path / "archive").glob("*")) == before
    async with session_factory() as session:
        await session.execute(
            sa.text(
                "DELETE FROM audit_logs WHERE action LIKE 'test.%' "
                "OR action = 'retention.run'"
            )
        )
        await session.commit()
