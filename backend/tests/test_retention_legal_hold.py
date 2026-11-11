"""S-98: retention email_outbox PII, legal hold и DSAR erase."""

import gzip
import json
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from domains.audit.models import AuditLog
from domains.auth.models import User
from domains.bot_lab.models import BotVersion
from domains.chess_lab.models import ChessGame
from domains.notifications.models import EmailOutbox
from domains.profile.models import UserProfile
from domains.pvp.models import PvpRating
from domains.python_teacher.models import (
    AssignmentLevel,
    PyAssignment,
    PySubmission,
    Verdict,
)
from domains.retention.models import LegalHold
from domains.retention.service import run_retention
from domains.review.models import ReviewCard
from domains.telegram.models import TelegramLink
from tests.conftest import API, make_direct_user


async def test_retention_email_outbox_metadata_deleted(tmp_path, monkeypatch):
    """S-98: метаданные старше 90 дней удаляются, архив без body."""
    kind = "test-retention-email-metadata"
    now = datetime(2026, 11, 8, tzinfo=UTC)
    old = now - timedelta(days=100)

    async with session_factory() as session:
        await session.execute(sa.delete(EmailOutbox).where(EmailOutbox.kind == kind))
        session.add_all(
            [
                EmailOutbox(
                    kind=kind,
                    recipient="parent@example.com",
                    subject="metadata sent",
                    body="secret-link",
                    status="sent",
                    attempts=1,
                    next_attempt_at=old,
                    created_at=old,
                    sent_at=old,
                ),
                EmailOutbox(
                    kind=kind,
                    recipient="parent@example.com",
                    subject="metadata failed",
                    body="secret-link-2",
                    status="failed",
                    attempts=8,
                    last_error="smtp down",
                    next_attempt_at=old,
                    created_at=old,
                ),
                EmailOutbox(
                    kind=kind,
                    recipient="parent@example.com",
                    subject="metadata pending",
                    body="keep-pending",
                    status="pending",
                    attempts=0,
                    next_attempt_at=old,
                    created_at=old,
                ),
            ]
        )
        await session.commit()

    monkeypatch.setattr(settings, "retention_archive_dir", str(tmp_path / "archive"))
    monkeypatch.setattr(settings, "email_outbox_body_retention_days", 30)
    monkeypatch.setattr(settings, "email_outbox_retention_days", 90)

    async with session_factory() as session:
        results = await run_retention(session, now=now)
        await session.commit()
        email_policy = next(
            item for item in results if item.policy == "email_outbox"
        )
        body_policy = next(
            item for item in results if item.policy == "email_outbox_body"
        )
        assert body_policy.scrubbed == 2
        assert email_policy.rows == 2
        assert email_policy.archived == 2
        assert email_policy.deleted == 2
        assert email_policy.archive_path is not None

        remaining = {
            row.subject: row.status
            for row in (
                await session.execute(
                    sa.select(EmailOutbox).where(EmailOutbox.kind == kind)
                )
            ).scalars()
        }
        assert remaining == {"metadata pending": "pending"}

        archives = list((tmp_path / "archive").glob("email_outbox-*.jsonl.gz"))
        assert archives
        with gzip.open(archives[0], "rt", encoding="utf-8") as handle:
            entries = [json.loads(line) for line in handle if line.strip()]
        assert entries
        assert all("body" not in item for item in entries)
        assert all(item["kind"] == kind for item in entries)

        await session.execute(sa.delete(EmailOutbox).where(EmailOutbox.kind == kind))
        await session.commit()


async def test_legal_hold_blocks_email_outbox_retention(
    admin_client, unique_email, tmp_path, monkeypatch
):
    """S-98: активный legal hold не даёт удалить/scrub email_outbox."""
    user_id = await make_direct_user(unique_email)
    kind = "test-legal-hold-email"
    now = datetime.now(UTC)
    old = now - timedelta(days=100)

    async with session_factory() as session:
        session.add(
            EmailOutbox(
                kind=kind,
                recipient=unique_email,
                subject="held consent",
                body="held-secret-link",
                status="sent",
                attempts=1,
                next_attempt_at=old,
                created_at=old,
                sent_at=old,
            )
        )
        await session.commit()

    monkeypatch.setattr(settings, "retention_archive_dir", str(tmp_path / "archive"))
    monkeypatch.setattr(settings, "email_outbox_body_retention_days", 30)
    monkeypatch.setattr(settings, "email_outbox_retention_days", 90)

    response = await admin_client.post(
        f"{API}/admin/legal-holds",
        json={
            "subjectType": "user",
            "subjectId": str(user_id),
            "reason": "litigation-hold",
        },
    )
    assert response.status_code == 201, response.text
    hold_id = int(response.json()["id"])

    try:
        async with session_factory() as session:
            await run_retention(session, now=now)
            await session.commit()
            row = (
                await session.execute(
                    sa.select(EmailOutbox).where(EmailOutbox.kind == kind)
                )
            ).scalar_one()
            assert row.body == "held-secret-link"
            skip = (
                await session.execute(
                    sa.select(AuditLog).where(
                        AuditLog.action == "retention.skipped_legal_hold",
                        AuditLog.target_id == str(user_id),
                    )
                )
            ).scalars().first()
            assert skip is not None

        response = await admin_client.delete(
            f"{API}/admin/legal-holds/{hold_id}"
        )
        assert response.status_code == 200, response.text

        async with session_factory() as session:
            await run_retention(session, now=now)
            await session.commit()
            gone = (
                await session.execute(
                    sa.select(EmailOutbox).where(EmailOutbox.kind == kind)
                )
            ).scalar_one_or_none()
            assert gone is None
    finally:
        async with session_factory() as session:
            await session.execute(
                sa.delete(EmailOutbox).where(EmailOutbox.kind == kind)
            )
            await session.execute(
                sa.delete(LegalHold).where(LegalHold.subject_id == str(user_id))
            )
            await session.commit()


async def test_erase_user_anonymizes_pii(admin_client, unique_email):
    """S-98: DSAR erase удаляет/обезличивает PII, audit остаётся."""
    user_id = await make_direct_user(unique_email)
    old_email = unique_email
    slug = f"erase-{unique_email.split('@')[0]}"

    async with session_factory() as session:
        assignment = PyAssignment(
            slug=slug,
            title="erase test",
            level=AssignmentLevel.NOVICE,
            topic="test",
            statement="erase",
            starter_code="",
            tests=[],
            checkpoints=[],
        )
        session.add(assignment)
        await session.flush()
        session.add_all(
            [
                EmailOutbox(
                    kind="test-erase-email",
                    recipient=old_email,
                    subject="erase",
                    body="pii-link",
                    status="sent",
                    attempts=1,
                ),
                TelegramLink(
                    user_id=user_id,
                    chat_id=f"chat-{unique_email}",
                    consent=True,
                ),
                ReviewCard(
                    user_id=user_id,
                    source_type="manual",
                    front="pii-front",
                    back="pii-back",
                ),
                PvpRating(user_id=user_id),
                BotVersion(
                    user_id=user_id,
                    version_no=1,
                    code="print('pii')",
                ),
                PySubmission(
                    assignment_id=assignment.id,
                    user_id=user_id,
                    code="print('pii-submission')",
                    verdict=Verdict.PASSED,
                    passed_tests=1,
                    total_tests=1,
                ),
                ChessGame(
                    user_id=user_id,
                    pgn="[Event \"pii\"]",
                ),
            ]
        )
        await session.commit()

    response = await admin_client.post(
        f"{API}/admin/users/{user_id}/erase",
        json={"reason": "GDPR data subject request"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True

    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert user.email == f"deleted-{user_id}@anon"
        assert user.is_active is False
        assert user.email_verified_at is None
        profile = await session.get(UserProfile, user_id)
        assert profile is not None and profile.prefs == {}

        outbox = (
            await session.execute(
                sa.select(EmailOutbox).where(
                    sa.func.lower(EmailOutbox.recipient) == old_email.lower()
                )
            )
        ).scalars().first()
        assert outbox is None
        telegram = await session.get(TelegramLink, user_id)
        assert telegram is None
        card = (
            await session.execute(
                sa.select(ReviewCard).where(ReviewCard.user_id == user_id)
            )
        ).scalars().first()
        assert card is None
        rating = await session.get(PvpRating, user_id)
        assert rating is None
        bot = (
            await session.execute(
                sa.select(BotVersion).where(BotVersion.user_id == user_id)
            )
        ).scalars().first()
        submission = (
            await session.execute(
                sa.select(PySubmission).where(PySubmission.user_id == user_id)
            )
        ).scalars().first()
        game = (
            await session.execute(
                sa.select(ChessGame).where(ChessGame.user_id == user_id)
            )
        ).scalars().first()
        assert bot is not None and bot.code == "# erased"
        assert submission is not None and submission.code == "# erased"
        assert game is not None and game.pgn == "# erased"

        audit = (
            await session.execute(
                sa.select(AuditLog).where(
                    AuditLog.action == "user.erased",
                    AuditLog.target_id == str(user_id),
                )
            )
        ).scalars().first()
        assert audit is not None
        assert audit.meta["reason"] == "GDPR data subject request"

    async with session_factory() as session:
        await session.execute(sa.delete(User).where(User.id == user_id))
        await session.commit()


async def test_erase_user_blocked_by_legal_hold(
    admin_client, unique_email
):
    """S-98: при активном hold DSAR erase возвращает 409."""
    user_id = await make_direct_user(unique_email)
    response = await admin_client.post(
        f"{API}/admin/legal-holds",
        json={
            "subjectType": "user",
            "subjectId": str(user_id),
            "reason": "legal-hold-before-erase",
        },
    )
    assert response.status_code == 201, response.text
    hold_id = int(response.json()["id"])
    try:
        response = await admin_client.post(
            f"{API}/admin/users/{user_id}/erase",
            json={"reason": "erase while held"},
        )
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "legal_hold_active"
        async with session_factory() as session:
            user = await session.get(User, user_id)
            assert user is not None and user.email == unique_email
    finally:
        await admin_client.delete(f"{API}/admin/legal-holds/{hold_id}")
        async with session_factory() as session:
            await session.execute(
                sa.delete(LegalHold).where(LegalHold.subject_id == str(user_id))
            )
            await session.commit()
