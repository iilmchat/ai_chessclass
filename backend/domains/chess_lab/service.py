"""Инсайт позиции (Design §6.2, сценарий B): факты SF → LLM-объяснение.

«LLM не правит факты»: движок Facts отдаются как блок (§6.2) и хранятся
отдельно от текста; ответ LLM — только объяснение.

Исполнение: SF — только воркер (§15.3). В api-роли задача уходит в arq
(`analyze_position`) и ждётся результат; в worker-роли (тесты/внутри
воркера) — прямой вызов движка.
"""

import logging

import chess
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from core.levels import LEVEL_TO_CHESS, Level, resolve_level
from domains.chess_lab.models import ChessPosition
from domains.profile.models import UserProfile
from engine.models import EngineLine
from llm.gateway import LLMCallContext, llm_generate
from llm.prompts.builder import build_messages

logger = logging.getLogger(__name__)

INSIGHT_TIMEOUT_S = 30.0
PIECE_VALUES = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9}


def material_balance(board: chess.Board) -> int:
    """Материал (пешечные единицы, +белым) — факт для панели."""
    balance = 0
    for piece in board.piece_map().values():
        value = PIECE_VALUES.get(piece.symbol().lower(), 0)
        balance += value if piece.color == chess.WHITE else -value
    return balance


def facts_to_lines(lines: list[EngineLine], fen: str) -> list[str]:
    """Человекочитаемые факты (панель + блок LLM, менять нельзя)."""
    board = chess.Board(fen)
    facts: list[str] = [f"Материал: {material_balance(board):+d} пешек"]
    for line in lines:
        if line.mate is not None:
            score = f"мат в {abs(line.mate)} за {'белых' if line.mate > 0 else 'чёрных'}"
        else:
            score = f"{line.score_cp:+d} сантипешек"
        facts.append(
            f"Лучший ход №{line.multipv}: {line.move_uci} ({score}), "
            f"глубина {line.depth}, PV: {' '.join(line.pv[:5])}"
        )
    return facts


def build_meta(
    lines: list[EngineLine], fen: str, explanation: str, level: Level
) -> dict:
    return {
        "facts": [line.model_dump() for line in lines],
        "factsText": facts_to_lines(lines, fen),
        "explanation": explanation,
        "level": level.value,
    }


async def run_engine_analysis(fen: str, level: Level) -> list[dict]:
    """Запуск анализа в допустимом контексте: worker — напрямую, api — arq.

    Уровень переводится в шахматный (ADR-002: novice→beginner и т.д.).
    Возвращает список фактов (JSON EngineLine). В api-роли задача уходит
    в arq и результат ждётся с таймаутом (§12.1 long-running).
    """
    chess_level = LEVEL_TO_CHESS[level]
    if settings.app_role == "worker":
        from engine.service import EngineService

        async with EngineService() as engine:
            lines = await engine.analyze(fen, chess_level, interactive=True)
        return [line.model_dump() for line in lines]

    # api: через arq-воркер (SF живёт только там)
    from arq.connections import RedisSettings, create_pool

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await pool.enqueue_job("analyze_position", fen, chess_level)
        if job is None:  # дубликат задачи уже в очереди
            raise AppError("task_busy", "Задача анализа уже выполняется", 409)
        result = await job.result(timeout=INSIGHT_TIMEOUT_S)
    except TimeoutError as exc:
        raise AppError("task_timeout", "Анализ не уложился в 30 с", 408) from exc
    finally:
        await pool.aclose()
    if isinstance(result, dict) and result.get("error"):
        raise AppError("engine_error", str(result["error"]), 502)
    if isinstance(result, dict):
        return list(result.get("facts") or [])
    return list(result or [])


async def insight(
    session: AsyncSession,
    redis,
    user,
    *,
    fen: str,
    level_override: str | None = None,
) -> dict:
    """POST /chess/insight {fen, level?} → факты SF + объяснение по уровню."""
    try:
        chess.Board(fen)
    except ValueError as exc:
        raise AppError("invalid_fen", f"Некорректный FEN: {fen!r}", 422) from exc

    profile = await session.get(UserProfile, user.id)
    profile_level = profile.level if profile is not None else Level.NOVICE
    level = resolve_level(profile_level, level_override)

    lines_raw = await run_engine_analysis(fen, level)

    from engine.models import EngineLine

    lines = [EngineLine(**item) for item in lines_raw]
    facts_text = facts_to_lines(lines, fen)

    # маршрут chess_lab.insight: L2 по умолчанию, L3 для advanced (§8.2);
    # правила уровня в промпте: «факты движка менять нельзя»
    messages = build_messages(
        "chess_lab.insight",
        level,
        request="Объясни позицию ученику простым языком.",
        facts=facts_text,
    )
    result = await llm_generate(
        session,
        redis,
        route="chess_lab.insight",
        level=level,
        messages=messages,
        ctx=LLMCallContext(user_id=user.id, billing_tier=_tier(profile)),
    )

    meta = build_meta(lines, fen, result.text, level)
    await _upsert_position(session, user.id, fen, meta)

    return {
        "fen": fen,
        "level": level.value,
        "facts": meta["facts"],
        "factsText": facts_text,
        "explanation": result.text,
        "modelUsed": result.model_used,
    }


def _tier(profile: UserProfile | None) -> str:
    return profile.billing_tier.value if profile is not None else "free"


async def _upsert_position(
    session: AsyncSession, user_id: int, fen: str, meta: dict
) -> None:
    stmt = pg_insert(ChessPosition).values(
        user_id=user_id, fen=fen, meta=meta
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "fen"],
        set_={"meta": meta},
    )
    await session.execute(stmt)


async def get_position(
    session: AsyncSession, user, position_id: int
) -> ChessPosition:
    position = await session.get(ChessPosition, position_id)
    if position is None or position.user_id != user.id:
        raise AppError("position_not_found", "Позиция не найдена", 404)
    return position


async def list_positions(
    session: AsyncSession, user, limit: int = 20
) -> list[ChessPosition]:
    stmt = (
        select(ChessPosition)
        .where(ChessPosition.user_id == user.id)
        .order_by(ChessPosition.id.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
