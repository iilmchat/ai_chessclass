"""S-46: observability summary, metrics, cost-per-student и alerts."""

import shutil
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from domains.auth.models import User
from domains.bot_lab.queues import MATCH_QUEUES, active_key
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
    retention_last = await retention.last_run(session)
    return {
        "db": db_ok,
        "redis": redis_ok,
        "queues": depths,
        "activeMatches": active,
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
    ]
    for queue, depth in data["queues"].items():
        lines.append(f'chessclass_queue_depth{{queue="{queue}"}} {depth}')
    for kind, active in data["activeMatches"].items():
        lines.append(f'chessclass_match_active{{kind="{kind}"}} {active}')
    return "\n".join(lines) + "\n"
