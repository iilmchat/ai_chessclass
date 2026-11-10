"""Реплей матча + SSE-поток прогресса (S-20)."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.authz import ensure_can_access_bot
from core.errors import AppError
from domains.bot_lab.models import BotMatch, BotMatchMove


async def get_replay(
    session: AsyncSession, user, bot_id: int, match_id: int
) -> dict:
    """Полный реплей: метаданные матча + ходы по порядку."""
    bot = await ensure_can_access_bot(user, bot_id, session)
    match = await session.get(BotMatch, match_id)
    if (
        match is None
        or match.version_id != bot_id
        or match.user_id != bot.user_id
    ):
        raise AppError("match_not_found", "Матч не найден", 404)
    moves = (
        await session.execute(
            select(BotMatchMove)
            .where(BotMatchMove.match_id == match_id)
            .order_by(BotMatchMove.ply)
        )
    ).scalars().all()
    return {
        "match": {
            "id": str(match.id),
            "opponent": match.opponent,
            "result": match.result.value,
            "movesCount": match.moves_count,
            "durationMs": match.duration_ms,
            "eloDelta": float(match.elo_delta),
            "startedAt": match.started_at.isoformat(),
            "finishedAt": (
                match.finished_at.isoformat() if match.finished_at else None
            ),
        },
        "moves": [
            {
                "ply": m.ply,
                "fen": m.fen,
                "uci": m.uci,
                "agent": m.agent,
                "thinkMs": m.think_ms,
            }
            for m in moves
        ],
    }


async def leaderboard(session: AsyncSession, limit: int = 10) -> list[dict]:
    """Лидерборд по Elo (v0.1: открытым списком — UX-решение §18.5)."""
    from domains.auth.models import User
    from domains.bot_lab.models import BotStats

    rows = (
        await session.execute(
            select(BotStats, User.email)
            .join(User, User.id == BotStats.user_id)
            .order_by(BotStats.elo.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "userId": str(stats.user_id),
            "email": email,
            "elo": float(stats.elo),
            "wins": stats.wins,
            "losses": stats.losses,
            "draws": stats.draws,
        }
        for stats, email in rows
    ]


def match_progress_payload(raw: str | bytes) -> dict:
    """Разобрать pubsub-сообщение прогресса (json)."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {"raw": str(raw)}
