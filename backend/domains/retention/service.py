"""S-46: retention/архив журналов, voice-кэша и черновиков этюдов."""

import gzip
import json
import logging
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from core.security import hash_password
from domains.audit import service as audit_svc
from domains.audit.models import AuditLog
from domains.auth.models import EmailToken, RefreshSession, User
from domains.bot_lab.models import BotVersion
from domains.chess_lab.models import ChessGame
from domains.consent.models import ParentalConsent
from domains.notifications.models import EmailOutbox
from domains.observability.models import FailedJob
from domains.profile.models import UserProfile
from domains.pvp.models import PvpRating
from domains.python_teacher.models import PySubmission
from domains.retention.models import LegalHold
from domains.review.models import ReviewCard
from domains.studies.models import ChessStudy, StudyStatus
from domains.telegram.models import TelegramLink, TelegramOutbox
from domains.voice.models import VoiceAudio
from domains.voice.usage import VoiceUsage
from llm.models import LLMCall

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetentionResult:
    policy: str
    cutoff: str
    rows: int
    archived: int
    deleted: int
    archive_path: str | None
    dry_run: bool
    scrubbed: int = 0


def _row_dict(row, exclude: tuple[str, ...] = ()) -> dict:
    return {
        column.key: getattr(row, column.key)
        for column in row.__table__.columns
        if column.key not in exclude
    }


def _archive(
    rows: list,
    policy: str,
    now: datetime,
    *,
    exclude: tuple[str, ...] = (),
) -> Path | None:
    if not rows:
        return None
    directory = Path(settings.retention_archive_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{policy}-{now.strftime('%Y%m%dT%H%M%SZ')}.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    _row_dict(row, exclude), ensure_ascii=False, default=str
                )
                + "\n"
            )
    return path


async def _process(
    session: AsyncSession,
    *,
    policy: str,
    rows: list,
    dry_run: bool,
    now: datetime,
    delete_files: bool = False,
    exclude: tuple[str, ...] = (),
) -> RetentionResult:
    archive_path = (
        None if dry_run else _archive(rows, policy, now, exclude=exclude)
    )
    deleted = 0
    if rows and not dry_run:
        ids = [row.id for row in rows]
        if delete_files:
            for row in rows:
                Path(row.path).unlink(missing_ok=True)
        await session.execute(
            delete(type(rows[0])).where(type(rows[0]).id.in_(ids))
        )
        deleted = len(rows)
        await session.flush()
    return RetentionResult(
        policy=policy,
        cutoff="",
        rows=len(rows),
        archived=len(rows) if archive_path else 0,
        deleted=deleted,
        archive_path=str(archive_path) if archive_path else None,
        dry_run=dry_run,
    )


def _active_hold_condition(now: datetime):
    return and_(
        LegalHold.revoked_at.is_(None),
        or_(LegalHold.expires_at.is_(None), LegalHold.expires_at > now),
    )


async def active_legal_holds(
    session: AsyncSession,
    *,
    subject_type: str | None = None,
    now: datetime | None = None,
) -> list[LegalHold]:
    now = now or datetime.now(UTC)
    stmt = select(LegalHold).where(_active_hold_condition(now))
    if subject_type:
        stmt = stmt.where(LegalHold.subject_type == subject_type)
    return list(
        (
            await session.execute(
                stmt.order_by(LegalHold.created_at.desc(), LegalHold.id.desc())
            )
        ).scalars()
    )


async def is_user_held(
    session: AsyncSession, user_id: int, *, now: datetime | None = None
) -> bool:
    now = now or datetime.now(UTC)
    row = await session.scalar(
        select(LegalHold.id)
        .where(
            _active_hold_condition(now),
            LegalHold.subject_type == "user",
            LegalHold.subject_id == str(user_id),
        )
        .limit(1)
    )
    return row is not None


async def count_active_holds(
    session: AsyncSession, *, now: datetime | None = None
) -> int:
    now = now or datetime.now(UTC)
    return int(
        await session.scalar(
            select(func.count())
            .select_from(LegalHold)
            .where(_active_hold_condition(now))
        )
        or 0
    )


async def _email_owner_ids(
    session: AsyncSession, emails: set[str]
) -> dict[str, int]:
    if not emails:
        return {}
    rows = await session.execute(
        select(User.id, func.lower(User.email)).where(
            func.lower(User.email).in_(sorted(emails))
        )
    )
    return {str(email): int(user_id) for user_id, email in rows}


async def _filter_held_email_rows(
    session: AsyncSession,
    rows: list[EmailOutbox],
    *,
    now: datetime,
) -> tuple[list[EmailOutbox], dict[int, int]]:
    """Разделить email-строки на разрешённые и удержанные legal hold."""
    owners = await _email_owner_ids(
        session, {row.recipient.strip().lower() for row in rows}
    )
    held = await active_legal_holds(session, subject_type="user", now=now)
    held_ids = {
        int(item.subject_id)
        for item in held
        if item.subject_id.isdigit()
    }
    kept: list[EmailOutbox] = []
    skipped: dict[int, int] = {}
    for row in rows:
        owner = owners.get(row.recipient.strip().lower())
        if owner is not None and owner in held_ids:
            skipped[owner] = skipped.get(owner, 0) + 1
        else:
            kept.append(row)
    return kept, skipped


async def _audit_skipped_holds(
    session: AsyncSession,
    *,
    policy: str,
    skipped: dict[int, int],
    now: datetime,
) -> None:
    for user_id, rows in sorted(skipped.items()):
        await audit_svc.record(
            session,
            None,
            "retention.skipped_legal_hold",
            target_type="user",
            target_id=user_id,
            source="system",
            meta={
                "policy": policy,
                "rows": rows,
                "checkedAt": now.isoformat(),
            },
        )


async def run_retention(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
) -> list[RetentionResult]:
    """Архивировать и удалить устаревшие данные по всем политикам."""
    now = now or datetime.now(UTC)
    batch = settings.retention_batch_size
    results: list[RetentionResult] = []

    policies: list[tuple[str, Any, datetime, bool]] = [
        (
            "audit_logs",
            AuditLog,
            now - timedelta(days=settings.audit_retention_days),
            False,
        ),
        (
            "llm_calls",
            LLMCall,
            now - timedelta(days=settings.llm_calls_retention_days),
            False,
        ),
        (
            "voice_audio",
            VoiceAudio,
            now - timedelta(days=settings.voice_retention_days),
            True,
        ),
        (
            "voice_usage",
            VoiceUsage,
            now - timedelta(days=settings.voice_retention_days),
            False,
        ),
    ]
    for policy, model, cutoff, delete_files in policies:
        rows = list(
            (
                await session.execute(
                    select(model)
                    .where(model.created_at < cutoff)
                    .order_by(model.created_at)
                    .limit(batch)
                )
            ).scalars()
        )
        result = await _process(
            session,
            policy=policy,
            rows=rows,
            dry_run=dry_run,
            now=now,
            delete_files=delete_files,
        )
        results.append(
            RetentionResult(
                **{**asdict(result), "cutoff": cutoff.isoformat()}
            )
        )

    studies_cutoff = now - timedelta(days=settings.studies_retention_days)
    studies = list(
        (
            await session.execute(
                select(ChessStudy)
                .where(
                    ChessStudy.created_at < studies_cutoff,
                    ChessStudy.status.in_(
                        [StudyStatus.DRAFT, StudyStatus.REJECTED]
                    ),
                )
                .order_by(ChessStudy.created_at)
                .limit(batch)
            )
        ).scalars()
    )
    result = await _process(
        session,
        policy="chess_studies",
        rows=studies,
        dry_run=dry_run,
        now=now,
    )
    results.append(
        RetentionResult(**{**asdict(result), "cutoff": studies_cutoff.isoformat()})
    )

    failed_cutoff = now - timedelta(days=settings.failed_jobs_retention_days)
    failed_jobs = list(
        (
            await session.execute(
                select(FailedJob)
                .where(FailedJob.failed_at < failed_cutoff)
                .order_by(FailedJob.failed_at)
                .limit(batch)
            )
        ).scalars()
    )
    result = await _process(
        session,
        policy="failed_jobs",
        rows=failed_jobs,
        dry_run=dry_run,
        now=now,
    )
    results.append(
        RetentionResult(**{**asdict(result), "cutoff": failed_cutoff.isoformat()})
    )

    # S-98: body (одноразовая ссылка/PII) чистим раньше метаданных.
    # Удержанные legal hold строки не трогаем; факт skip — в audit_logs.
    body_cutoff = now - timedelta(
        days=settings.email_outbox_body_retention_days
    )
    body_candidates = list(
        (
            await session.execute(
                select(EmailOutbox)
                .where(
                    EmailOutbox.status.in_(("sent", "failed")),
                    func.coalesce(
                        EmailOutbox.sent_at, EmailOutbox.created_at
                    )
                    < body_cutoff,
                    EmailOutbox.body != "[deleted]",
                )
                .order_by(EmailOutbox.id)
                .limit(batch)
            )
        ).scalars()
    )
    body_rows, body_skipped = await _filter_held_email_rows(
        session, body_candidates, now=now
    )
    body_scrubbed = 0
    if body_rows and not dry_run:
        ids = [row.id for row in body_rows]
        await session.execute(
            update(EmailOutbox)
            .where(EmailOutbox.id.in_(ids))
            .values(body="[deleted]")
        )
        body_scrubbed = len(ids)
        await session.flush()
    results.append(
        RetentionResult(
            policy="email_outbox_body",
            cutoff=body_cutoff.isoformat(),
            rows=len(body_rows),
            archived=0,
            deleted=0,
            archive_path=None,
            dry_run=dry_run,
            scrubbed=body_scrubbed,
        )
    )
    await _audit_skipped_holds(
        session,
        policy="email_outbox_body",
        skipped=body_skipped,
        now=now,
    )

    # Метаданные (без body) удаляем после 90 дней; архив — без body.
    email_cutoff = now - timedelta(days=settings.email_outbox_retention_days)
    email_candidates = list(
        (
            await session.execute(
                select(EmailOutbox)
                .where(
                    EmailOutbox.status.in_(("sent", "failed")),
                    func.coalesce(
                        EmailOutbox.sent_at, EmailOutbox.created_at
                    )
                    < email_cutoff,
                )
                .order_by(EmailOutbox.id)
                .limit(batch)
            )
        ).scalars()
    )
    email_rows, email_skipped = await _filter_held_email_rows(
        session, email_candidates, now=now
    )
    result = await _process(
        session,
        policy="email_outbox",
        rows=email_rows,
        dry_run=dry_run,
        now=now,
        exclude=("body",),
    )
    results.append(
        RetentionResult(**{**asdict(result), "cutoff": email_cutoff.isoformat()})
    )
    await _audit_skipped_holds(
        session,
        policy="email_outbox",
        skipped=email_skipped,
        now=now,
    )

    if not dry_run:
        await audit_svc.record(
            session,
            None,
            "retention.run",
            source="system",
            meta={
                "policies": {
                    item.policy: {
                        "rows": item.rows,
                        "deleted": item.deleted,
                        "scrubbed": item.scrubbed,
                        "archivePath": item.archive_path,
                    }
                    for item in results
                }
            },
        )
        await session.flush()
    logger.info(
        "retention: %s",
        {
            item.policy: (item.rows, item.deleted, item.scrubbed)
            for item in results
        },
    )
    return results


def _rowcount(result: Any) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


async def erase_user(
    session: AsyncSession,
    user_id: int,
    *,
    reason: str,
    now: datetime | None = None,
) -> dict[str, int]:
    """DSAR erase: анонимизировать users и удалить/обезличить PII.

    Legal hold проверяется до любых изменений; при активном hold —
    409 `legal_hold_active`. audit_logs/llm_calls/legal_holds не трогаем.
    """
    now = now or datetime.now(UTC)
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("user_not_found", "Пользователь не найден", 404)
    if await is_user_held(session, user_id, now=now):
        raise AppError(
            "legal_hold_active",
            "Активен legal hold: erase запрещён до отзыва",
            409,
        )

    old_email = user.email.strip().lower()
    counts: dict[str, int] = {}

    async def _delete(model, *conditions) -> None:
        result = await session.execute(delete(model).where(*conditions))
        counts[model.__tablename__] = _rowcount(result)

    await _delete(EmailOutbox, func.lower(EmailOutbox.recipient) == old_email)
    await _delete(EmailToken, EmailToken.user_id == user_id)
    await _delete(RefreshSession, RefreshSession.user_id == user_id)
    await _delete(TelegramLink, TelegramLink.user_id == user_id)
    await _delete(TelegramOutbox, TelegramOutbox.user_id == user_id)
    await _delete(ReviewCard, ReviewCard.user_id == user_id)
    await _delete(PvpRating, PvpRating.user_id == user_id)

    bot_result = await session.execute(
        update(BotVersion)
        .where(BotVersion.user_id == user_id)
        .values(code="# erased")
    )
    counts["bot_versions"] = _rowcount(bot_result)
    submission_result = await session.execute(
        update(PySubmission)
        .where(PySubmission.user_id == user_id)
        .values(code="# erased")
    )
    counts["py_submissions"] = _rowcount(submission_result)
    game_result = await session.execute(
        update(ChessGame)
        .where(ChessGame.user_id == user_id)
        .values(pgn="# erased")
    )
    counts["chess_games"] = _rowcount(game_result)

    profile = await session.get(UserProfile, user_id)
    if profile is not None:
        profile.display_name = None
        profile.prefs = {}
    consent_result = await session.execute(
        update(ParentalConsent)
        .where(ParentalConsent.user_id == user_id)
        .values(parent_email=f"deleted-{user_id}@anon")
    )
    counts["parental_consents"] = _rowcount(consent_result)

    user.email = f"deleted-{user_id}@anon"
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.is_active = False
    user.email_verified_at = None
    await session.flush()
    logger.info("dsar: erased user_id=%s reason=%s", user_id, reason[:120])
    return counts


async def retention_counts(
    session: AsyncSession, *, now: datetime | None = None
) -> list[dict]:
    now = now or datetime.now(UTC)
    checks: list[tuple[str, Any, int, Any]] = [
        ("audit_logs", AuditLog, settings.audit_retention_days, AuditLog.created_at),
        ("llm_calls", LLMCall, settings.llm_calls_retention_days, LLMCall.created_at),
        (
            "voice_audio",
            VoiceAudio,
            settings.voice_retention_days,
            VoiceAudio.created_at,
        ),
        (
            "voice_usage",
            VoiceUsage,
            settings.voice_retention_days,
            VoiceUsage.created_at,
        ),
        (
            "chess_studies",
            ChessStudy,
            settings.studies_retention_days,
            ChessStudy.created_at,
        ),
        (
            "failed_jobs",
            FailedJob,
            settings.failed_jobs_retention_days,
            FailedJob.failed_at,
        ),
        (
            "email_outbox_body",
            EmailOutbox,
            settings.email_outbox_body_retention_days,
            func.coalesce(EmailOutbox.sent_at, EmailOutbox.created_at),
        ),
        (
            "email_outbox",
            EmailOutbox,
            settings.email_outbox_retention_days,
            func.coalesce(EmailOutbox.sent_at, EmailOutbox.created_at),
        ),
    ]
    out: list[dict] = []
    for policy, model, days, time_col in checks:
        cutoff = now - timedelta(days=days)
        stmt = select(func.count()).select_from(model).where(time_col < cutoff)
        if policy == "chess_studies":
            stmt = stmt.where(
                ChessStudy.status.in_([StudyStatus.DRAFT, StudyStatus.REJECTED])
            )
        elif policy in {"email_outbox", "email_outbox_body"}:
            stmt = stmt.where(EmailOutbox.status.in_(("sent", "failed")))
        if policy == "email_outbox_body":
            stmt = stmt.where(EmailOutbox.body != "[deleted]")
        count = int(await session.scalar(stmt) or 0)
        out.append(
            {
                "policy": policy,
                "retentionDays": days,
                "cutoff": cutoff.isoformat(),
                "rows": count,
            }
        )
    return out


async def last_run(session: AsyncSession) -> dict | None:
    row = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.action == "retention.run")
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "at": row.created_at,
        "meta": row.meta,
    }
