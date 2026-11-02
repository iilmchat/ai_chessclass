"""S-46: retention/архив журналов, voice-кэша и черновиков этюдов."""

import gzip
import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from domains.audit import service as audit_svc
from domains.audit.models import AuditLog
from domains.studies.models import ChessStudy, StudyStatus
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


def _row_dict(row) -> dict:
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


def _archive(rows: list, policy: str, now: datetime) -> Path | None:
    if not rows:
        return None
    directory = Path(settings.retention_archive_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{policy}-{now.strftime('%Y%m%dT%H%M%SZ')}.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(_row_dict(row), ensure_ascii=False, default=str) + "\n"
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
) -> RetentionResult:
    archive_path = None if dry_run else _archive(rows, policy, now)
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
                        "archivePath": item.archive_path,
                    }
                    for item in results
                }
            },
        )
        await session.flush()
    logger.info(
        "retention: %s",
        {item.policy: (item.rows, item.deleted) for item in results},
    )
    return results


async def retention_counts(
    session: AsyncSession, *, now: datetime | None = None
) -> list[dict]:
    now = now or datetime.now(UTC)
    checks: list[tuple[str, Any, int]] = [
        ("audit_logs", AuditLog, settings.audit_retention_days),
        ("llm_calls", LLMCall, settings.llm_calls_retention_days),
        ("voice_audio", VoiceAudio, settings.voice_retention_days),
        ("voice_usage", VoiceUsage, settings.voice_retention_days),
        ("chess_studies", ChessStudy, settings.studies_retention_days),
    ]
    out: list[dict] = []
    for policy, model, days in checks:
        cutoff = now - timedelta(days=days)
        stmt = select(func.count()).select_from(model).where(model.created_at < cutoff)
        if policy == "chess_studies":
            stmt = stmt.where(
                ChessStudy.status.in_([StudyStatus.DRAFT, StudyStatus.REJECTED])
            )
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
