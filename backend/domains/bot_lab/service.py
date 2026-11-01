"""Сервис bot_lab: версии ботов, запуск хода в песочнице."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from domains.bot_lab.models import BotVersion
from domains.bot_lab.runner import run_bot_move

logger = logging.getLogger(__name__)


async def list_bots(session: AsyncSession, user) -> list[BotVersion]:
    stmt = (
        select(BotVersion)
        .where(BotVersion.user_id == user.id, BotVersion.is_active.is_(True))
        .order_by(BotVersion.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_bot(session: AsyncSession, user, bot_id: int) -> BotVersion:
    bot = await session.get(BotVersion, bot_id)
    if bot is None or bot.user_id != user.id:
        raise AppError("bot_not_found", "Бот не найден", 404)
    return bot


async def create_bot(
    session: AsyncSession, user, code: str, entry: str = "choose_move"
) -> BotVersion:
    max_no = (
        await session.execute(
            select(func.max(BotVersion.version_no)).where(
                BotVersion.user_id == user.id
            )
        )
    ).scalar_one()
    bot = BotVersion(
        user_id=user.id,
        version_no=(max_no or 0) + 1,
        code=code,
        entry=entry,
    )
    session.add(bot)
    await session.flush()
    return bot


async def test_move(
    session: AsyncSession, user, bot_id: int, fen: str
) -> dict:
    """Тест одного хода бота в песочнице (per-move 1.0 c, §8 bot_lab)."""
    bot = await get_bot(session, user, bot_id)
    result = await run_bot_move(
        bot.code,
        bot.entry,
        fen,
        timeout_s=settings.bot_permove_timeout_s,
        memory_limit_mb=settings.sandbox_memory_limit_mb,
        max_output_chars=settings.sandbox_max_output_chars,
    )
    if result["errorType"] == "SecurityError":
        raise AppError("bot_restricted", str(result["error"]), 422)
    if result["errorType"] == "TimeoutError":
        raise AppError("bot_timeout", str(result["error"]), 408)
    if not result["ok"]:
        raise AppError("bot_error", str(result["error"]), 422)
    return result
