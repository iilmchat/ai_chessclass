"""S-46: observability summary, metrics, cost-per-student и alerts."""

import json
import shutil
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.http_metrics import render_http_metrics
from domains.auth.models import User
from domains.bot_lab.queues import MATCH_QUEUES, active_key
from domains.notifications.models import EmailOutbox
from domains.observability.models import FailedJob
from domains.retention import service as retention
from domains.telegram.models import TelegramOutbox
from domains.voice.usage import VoiceUsage
from llm.models import LLMCall


async def _db_ok(session: AsyncSession) -> bool:
    try:
        await session.execute(text("select 1"))
        return True
    except Exception:  # noqa: BLE001 - health не должен падать
        return False


async def _redis_ok(redis) -> bool:
    try:
        return bool(await redis.ping())
    except Exception:  # noqa: BLE001
        return False


async def _queues(redis) -> tuple[dict[str, int], dict[str, int]]:
    async def safe_len(key: str) -> int:
        try:
            return int(await redis.llen(key) or 0)
        except Exception:  # noqa: BLE001 - ключ может быть занят не списком
            return 0

    async def safe_card(key: str) -> int:
        try:
            return int(await redis.scard(key) or 0)
        except Exception:  # noqa: BLE001 - ключ может быть не set
            return 0

    depths = {"arq:queue": await safe_len("arq:queue")}
    active = {}
    for kind, (queue, _limit) in MATCH_QUEUES.items():
        depths[queue] = await safe_len(queue)
        active[kind] = await safe_card(active_key(kind))
    return depths, active


async def _email_outbox_stats(session: AsyncSession) -> tuple[int, float]:
    """S-88: pending + parked failed и возраст самой старой недоставленной строки.

    `pending_total` — то, что ещё ждёт доставки: все pending плюс `failed`,
    исчерпавшие `EMAIL_OUTBOX_MAX_ATTEMPTS` (такие строки «припаркованы» на год
    и сами не повторятся). Retryable `failed` (attempts < max) считаются
    «pending» для возраста: письмо всё ещё не доставлено.
    """
    pending_total = int(
        await session.scalar(
            select(func.count())
            .select_from(EmailOutbox)
            .where(
                or_(
                    EmailOutbox.status == "pending",
                    and_(
                        EmailOutbox.status == "failed",
                        EmailOutbox.attempts >= settings.email_outbox_max_attempts,
                    ),
                )
            )
        )
        or 0
    )
    oldest = await session.scalar(
        select(func.min(EmailOutbox.created_at)).where(
            EmailOutbox.status.in_(("pending", "failed")),
            EmailOutbox.attempts < settings.email_outbox_max_attempts,
        )
    )
    oldest_age = 0.0
    if oldest is not None:
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=UTC)
        oldest_age = max(0.0, (datetime.now(UTC) - oldest).total_seconds())
    return pending_total, oldest_age


def _backup_status() -> tuple[float, int]:
    """S-93: (last_success_ts, restore_ok) из статуса backup-скриптов.

    Нет файла/поля restore — restore_ok=1 (не алертим до первого restore-test);
    backup timestamp=0 (алерт BackupFailed сработает, если успешного бэкапа
    ещё не было или он старше 25 ч).
    """
    path = Path(settings.backup_status_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return 0.0, 1
    try:
        last = float(data.get("last_success_timestamp") or 0)
    except (TypeError, ValueError):
        last = 0.0
    restore_ok = 0 if data.get("last_restore_ok") is False else 1
    return max(0.0, last), restore_ok


def _retention_archive_age_seconds(now: datetime) -> float:
    """S-88: возраст последнего gzip-архива retention; 0 — архивов ещё нет."""
    directory = Path(settings.retention_archive_dir)
    try:
        archives = [
            item
            for item in directory.iterdir()
            if item.is_file() and item.name.endswith(".jsonl.gz")
        ]
    except OSError:
        return 0.0
    if not archives:
        return 0.0
    try:
        latest = max(item.stat().st_mtime for item in archives)
    except OSError:
        return 0.0
    return max(0.0, now.timestamp() - latest)


async def summary(session: AsyncSession, redis) -> dict:
    db_ok = await _db_ok(session)
    redis_ok = await _redis_ok(redis)
    depths, active = await _queues(redis) if redis_ok else ({}, {})
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    llm_cost, tokens_in, tokens_out = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(LLMCall.cost_in, 0)
                        + func.coalesce(LLMCall.cost_out, 0)
                    ),
                    0,
                ),
                func.coalesce(func.sum(LLMCall.tokens_in), 0),
                func.coalesce(func.sum(LLMCall.tokens_out), 0),
            ).where(LLMCall.created_at >= today)
        )
    ).one()
    voice_chars, voice_cost = (
        await session.execute(
            select(
                func.coalesce(func.sum(VoiceUsage.chars), 0),
                func.coalesce(func.sum(VoiceUsage.cost), 0),
            ).where(VoiceUsage.created_at >= today)
        )
    ).one()
    archive_dir = Path(settings.retention_archive_dir)
    try:
        free_gb = shutil.disk_usage(archive_dir if archive_dir.exists() else "/").free / 1e9
    except OSError:
        free_gb = 0.0
    failed_jobs = int(
        await session.scalar(
            select(func.count())
            .select_from(FailedJob)
            .where(FailedJob.status == "failed")
        )
        or 0
    )
    retention_last = await retention.last_run(session)
    return {
        "db": db_ok,
        "redis": redis_ok,
        "queues": depths,
        "activeMatches": active,
        "failedJobs": failed_jobs,
        "llmCostTodayRub": float(llm_cost),
        "llmTokensToday": int(tokens_in) + int(tokens_out),
        "voiceCharsToday": int(voice_chars),
        "voiceCostTodayRub": float(voice_cost),
        "diskFreeGb": round(free_gb, 2),
        "retentionLastRun": (
            retention_last["at"].isoformat() if retention_last else None
        ),
    }


async def alerts(session: AsyncSession, redis) -> list[dict]:
    data = await summary(session, redis)
    out: list[dict] = []
    if not data["db"]:
        out.append({"code": "db_down", "severity": "critical", "message": "PostgreSQL недоступен"})
    if not data["redis"]:
        out.append({"code": "redis_down", "severity": "critical", "message": "Redis недоступен"})
    if data["diskFreeGb"] < settings.obs_disk_min_free_gb:
        out.append(
            {
                "code": "disk_low",
                "severity": "warning",
                "message": f"Свободно {data['diskFreeGb']} GB (< {settings.obs_disk_min_free_gb})",
            }
        )
    for queue, depth in data["queues"].items():
        if depth > settings.obs_queue_alert_depth:
            out.append(
                {
                    "code": "queue_backlog",
                    "severity": "warning",
                    "message": f"{queue}: очередь {depth}",
                }
            )
    if data["llmCostTodayRub"] > settings.obs_llm_cost_alert_rub:
        out.append(
            {
                "code": "llm_cost",
                "severity": "warning",
                "message": f"LLM сегодня {data['llmCostTodayRub']:.2f} ₽",
            }
        )
    if data["failedJobs"] > settings.obs_failed_jobs_alert_threshold:
        out.append(
            {
                "code": "failed_jobs_growth",
                "severity": "warning",
                "message": (
                    f"DLQ: {data['failedJobs']} failed jobs "
                    f"(> {settings.obs_failed_jobs_alert_threshold})"
                ),
            }
        )
    if settings.obs_tls_cert_path:
        cert_path = Path(settings.obs_tls_cert_path)
        if cert_path.is_file():
            try:
                info = ssl._ssl._test_decode_cert(str(cert_path))  # type: ignore[attr-defined]
                not_after = ssl.cert_time_to_seconds(info["notAfter"])
                days_left = int((not_after - datetime.now(UTC).timestamp()) / 86400)
                if days_left < 30:
                    out.append(
                        {
                            "code": "tls_expiry",
                            "severity": "warning" if days_left >= 0 else "critical",
                            "message": f"TLS истекает через {days_left} дн.",
                        }
                    )
            except Exception:  # noqa: BLE001
                out.append(
                    {
                        "code": "tls_unreadable",
                        "severity": "warning",
                        "message": "Не удалось прочитать TLS-сертификат",
                    }
                )
    last = data["retentionLastRun"]
    if last is None:
        out.append(
            {
                "code": "retention_never_run",
                "severity": "info",
                "message": "Retention ещё не запускался",
            }
        )
    else:
        last_dt = datetime.fromisoformat(last)
        if datetime.now(UTC) - last_dt > timedelta(days=2):
            out.append(
                {
                    "code": "retention_stale",
                    "severity": "warning",
                    "message": "Retention не запускался > 2 дней",
                }
            )

    # --- S-68: тихие отказы интеграций ---
    telegram_failed = (
        await session.execute(
            select(func.count())
            .select_from(TelegramOutbox)
            .where(TelegramOutbox.status == "failed")
        )
    ).scalar_one()
    if telegram_failed > 0:
        out.append(
            {
                "code": "telegram_outbox_failed",
                "severity": "warning",
                "message": f"Telegram outbox: {telegram_failed} failed",
            }
        )
    from domains.lms.models import LrsDelivery

    lrs_failed = (
        await session.execute(
            select(func.count())
            .select_from(LrsDelivery)
            .where(LrsDelivery.status == "failed")
        )
    ).scalar_one()
    if lrs_failed > 0:
        out.append(
            {
                "code": "lrs_deliveries_failed",
                "severity": "warning",
                "message": f"LRS deliveries: {lrs_failed} failed",
            }
        )
    return out


async def failed_jobs(
    session: AsyncSession, *, status: str | None = "failed", limit: int = 50
) -> list[FailedJob]:
    stmt = (
        select(FailedJob)
        .order_by(FailedJob.failed_at.desc(), FailedJob.id.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(FailedJob.status == status)
    return list((await session.execute(stmt)).scalars())


async def failed_job(session: AsyncSession, row_id: int) -> FailedJob | None:
    return await session.get(FailedJob, row_id)


async def costs(session: AsyncSession, days: int = 30) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=days)
    llm_rows = (
        await session.execute(
            select(
                LLMCall.user_id,
                func.coalesce(
                    func.sum(
                        func.coalesce(LLMCall.cost_in, 0)
                        + func.coalesce(LLMCall.cost_out, 0)
                    ),
                    0,
                ),
                func.coalesce(func.sum(LLMCall.tokens_in), 0),
                func.coalesce(func.sum(LLMCall.tokens_out), 0),
            )
            .where(LLMCall.created_at >= since, LLMCall.user_id.is_not(None))
            .group_by(LLMCall.user_id)
        )
    ).all()
    voice_rows = (
        await session.execute(
            select(
                VoiceUsage.user_id,
                func.coalesce(func.sum(VoiceUsage.chars), 0),
                func.coalesce(func.sum(VoiceUsage.cost), 0),
            )
            .where(VoiceUsage.created_at >= since)
            .group_by(VoiceUsage.user_id)
        )
    ).all()
    llm = {
        int(user_id): (float(cost or 0), int(t_in or 0), int(t_out or 0))
        for user_id, cost, t_in, t_out in llm_rows
        if user_id is not None
    }
    voice = {
        int(user_id): (int(chars or 0), float(cost or 0))
        for user_id, chars, cost in voice_rows
    }
    user_ids = set(llm) | set(voice)
    if not user_ids:
        return []
    users = {
        int(user.id): user
        for user in (
            await session.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars()
    }
    out = []
    for user_id in sorted(user_ids):
        llm_cost, t_in, t_out = llm.get(user_id, (0.0, 0, 0))
        chars, voice_cost = voice.get(user_id, (0, 0.0))
        user = users.get(user_id)
        out.append(
            {
                "userId": str(user_id),
                "email": user.email if user else None,
                "llmCostRub": round(llm_cost, 4),
                "voiceChars": chars,
                "voiceCostRub": round(voice_cost, 4),
                "totalCostRub": round(llm_cost + voice_cost, 4),
                "tokensIn": t_in,
                "tokensOut": t_out,
            }
        )
    return sorted(out, key=lambda row: row["totalCostRub"], reverse=True)


async def metrics_text(session: AsyncSession, redis) -> str:
    data = await summary(session, redis)
    outbox_pending, outbox_oldest_age = await _email_outbox_stats(session)
    archive_age = _retention_archive_age_seconds(datetime.now(UTC))
    backup_last, backup_restore_ok = _backup_status()
    lines = [
        "# HELP chessclass_up ChessClass process up",
        "# TYPE chessclass_up gauge",
        "chessclass_up 1",
        "# HELP chessclass_db_up PostgreSQL availability",
        "# TYPE chessclass_db_up gauge",
        f"chessclass_db_up {1 if data['db'] else 0}",
        "# HELP chessclass_redis_up Redis availability",
        "# TYPE chessclass_redis_up gauge",
        f"chessclass_redis_up {1 if data['redis'] else 0}",
        "# HELP chessclass_llm_cost_today_rub LLM cost today",
        "# TYPE chessclass_llm_cost_today_rub gauge",
        f"chessclass_llm_cost_today_rub {data['llmCostTodayRub']}",
        "# HELP chessclass_llm_tokens_today LLM tokens today",
        "# TYPE chessclass_llm_tokens_today gauge",
        f"chessclass_llm_tokens_today {data['llmTokensToday']}",
        "# HELP chessclass_voice_chars_today Voice characters today",
        "# TYPE chessclass_voice_chars_today gauge",
        f"chessclass_voice_chars_today {data['voiceCharsToday']}",
        "# HELP chessclass_voice_cost_today_rub Voice cost today",
        "# TYPE chessclass_voice_cost_today_rub gauge",
        f"chessclass_voice_cost_today_rub {data['voiceCostTodayRub']}",
        "# HELP chessclass_disk_free_gb Free disk space",
        "# TYPE chessclass_disk_free_gb gauge",
        f"chessclass_disk_free_gb {data['diskFreeGb']}",
        "# HELP chessclass_failed_jobs Failed arq jobs",
        "# TYPE chessclass_failed_jobs gauge",
        f"chessclass_failed_jobs {data['failedJobs']}",
        "# HELP chessclass_email_outbox_pending_total Undelivered emails (pending + parked failed)",
        "# TYPE chessclass_email_outbox_pending_total gauge",
        f"chessclass_email_outbox_pending_total {outbox_pending}",
        "# HELP chessclass_email_outbox_oldest_pending_age_seconds Age of oldest undelivered email",
        "# TYPE chessclass_email_outbox_oldest_pending_age_seconds gauge",
        (
            "chessclass_email_outbox_oldest_pending_age_seconds "
            f"{round(outbox_oldest_age, 3)}"
        ),
        "# HELP chessclass_retention_archive_age_seconds Age of latest retention gzip archive",
        "# TYPE chessclass_retention_archive_age_seconds gauge",
        (
            "chessclass_retention_archive_age_seconds "
            f"{round(archive_age, 3)}"
        ),
        (
            "# HELP chessclass_backup_last_success_timestamp_seconds "
            "Unix ts of last successful offsite backup"
        ),
        "# TYPE chessclass_backup_last_success_timestamp_seconds gauge",
        (
            "chessclass_backup_last_success_timestamp_seconds "
            f"{round(backup_last, 3)}"
        ),
        "# HELP chessclass_backup_restore_ok Last restore-test result (1/0)",
        "# TYPE chessclass_backup_restore_ok gauge",
        f"chessclass_backup_restore_ok {backup_restore_ok}",
    ]
    for queue, depth in data["queues"].items():
        lines.append(f'chessclass_queue_depth{{queue="{queue}"}} {depth}')
    for kind, active in data["activeMatches"].items():
        lines.append(f'chessclass_match_active{{kind="{kind}"}} {active}')
    return "\n".join(lines) + "\n" + render_http_metrics()
