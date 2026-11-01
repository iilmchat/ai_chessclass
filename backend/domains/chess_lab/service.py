"""Инсайт позиции и анализ партий (Design §6.2).

«LLM не правит факты»: факты движка хранятся отдельно от текста LLM.

Исполнение: SF — только воркер (§15.3). В api-роли задачи уходят в arq
(`analyze_position`, `analyze_game`) и ждутся/опрашиваются; в worker-роли
(тесты/внутри воркера) — прямой вызов движка.
"""

import asyncio
import json
import logging

import chess
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from core.levels import LEVEL_TO_CHESS, Level, resolve_level
from domains.chess_lab.classifier import classify_move
from domains.chess_lab.ingestion import InvalidPgnError, parse_pgn
from domains.chess_lab.models import (
    AnalysisStatus,
    ChessAnalysis,
    ChessGame,
    ChessPosition,
)
from domains.profile.models import UserProfile
from engine.models import EngineLine
from llm.gateway import LLMCallContext, llm_generate
from llm.prompts.builder import build_messages

logger = logging.getLogger(__name__)

INSIGHT_TIMEOUT_S = 30.0
GAME_ANALYSIS_TIMEOUT_S = 300.0
PROGRESS_CHANNEL = "chess:progress:{game_id}"
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


# --- анализ партий (S-12, §6.2)


async def upload_game(session: AsyncSession, user, pgn: str) -> dict:
    """Upload PGN (≤ 2 МБ) → parse → chess_games + analysis(pending) → arq."""
    if len(pgn.encode("utf-8")) > settings.chess_pgn_max_bytes:
        raise AppError("pgn_too_large", "PGN больше 2 МБ", 422)
    try:
        parse_pgn(pgn)  # валидация до записи в БД
    except InvalidPgnError as exc:
        raise AppError("invalid_pgn", str(exc), 422) from exc

    game = ChessGame(user_id=user.id, pgn=pgn)
    session.add(game)
    await session.flush()
    session.add(ChessAnalysis(game_id=game.id))
    await session.flush()

    from arq.connections import RedisSettings, create_pool

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("analyze_game", game.id)
    finally:
        await pool.aclose()

    logger.info("chess: партия game_id=%s поставлена в анализ", game.id)
    return {"game_id": game.id, "status": AnalysisStatus.PENDING.value}


async def get_analysis_for_user(session: AsyncSession, user, game_id: int) -> ChessAnalysis:
    game = await session.get(ChessGame, game_id)
    if game is None or game.user_id != user.id:
        raise AppError("game_not_found", "Партия не найдена", 404)
    analysis = (
        await session.execute(
            select(ChessAnalysis).where(ChessAnalysis.game_id == game_id)
        )
    ).scalar_one_or_none()
    if analysis is None:
        raise AppError("analysis_not_found", "Разбор не начат", 404)
    return analysis


async def get_blunders(session: AsyncSession, user, game_id: int) -> dict:
    """Blunders партии: SF-факты + сохранённые LLM-объяснения."""
    analysis = await get_analysis_for_user(session, user, game_id)
    blunders = list(analysis.sf.get("blunders") or [])
    explanations = analysis.llm.get("blunders") or {}
    for item in blunders:
        item["explanation"] = explanations.get(str(item["ply"]))
    return {
        "game_id": game_id,
        "status": analysis.status.value,
        "blunders": blunders,
        "summary": analysis.sf.get("summary") or {},
    }


async def explain_blunder(
    session: AsyncSession, redis, user, game_id: int, ply: int
) -> dict:
    """LLM-объяснение блюндера (маршрут chess_lab.blunder, L2)."""
    analysis = await get_analysis_for_user(session, user, game_id)
    if analysis.status is not AnalysisStatus.DONE:
        raise AppError("analysis_not_done", "Разбор партии ещё не завершён", 409)
    blunder = next(
        (b for b in analysis.sf.get("blunders") or [] if b["ply"] == ply), None
    )
    if blunder is None:
        raise AppError(
            "blunder_not_found", f"Блюндер на полуходе {ply} не найден", 404
        )

    profile = await session.get(UserProfile, user.id)
    level = profile.level if profile is not None else Level.NOVICE
    messages = build_messages(
        "chess_lab.blunder",
        level,
        request=(
            f"Объясни, почему ход {blunder['playedSan']} — блюндер, и что было лучше."
        ),
        facts=[
            f"Позиция до хода (FEN): {blunder['fenBefore']}",
            f"Сыграно: {blunder['playedSan']} ({blunder['playedUci']})",
            f"Лучше было: {blunder['bestSan']} ({blunder['bestUci']})",
            f"Потеря: {blunder['deltaCp']} сантипешек",
        ],
    )
    result = await llm_generate(
        session,
        redis,
        route="chess_lab.blunder",
        level=level,
        messages=messages,
        ctx=LLMCallContext(user_id=user.id, billing_tier=_tier(profile)),
    )

    llm_block = dict(analysis.llm)
    blunder_map = dict(llm_block.get("blunders") or {})
    blunder_map[str(ply)] = result.text
    llm_block["blunders"] = blunder_map
    analysis.llm = llm_block
    await session.flush()
    return {
        "ply": ply,
        "explanation": result.text,
        "model_used": result.model_used,
    }


def progress_channel(game_id: int) -> str:
    return f"chess:progress:{game_id}"


def _san_of(board: chess.Board, uci: str) -> str:
    """SAN хода по UCI в позиции (ход обязан быть легальным)."""
    move = board.parse_uci(uci)
    return board.san(move)


def _terminal_score(board: chess.Board) -> int | None:
    """Оценка конечной позиции (движок её не анализирует): мат/ничья.

    Возвращает сантипешки с точки зрения белых или None (не терминальная).
    """
    if board.is_checkmate():
        # ходить тому, кому заматован: белые выиграли → +9900
        return 9900 if board.turn == chess.BLACK else -9900
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
    return None


async def analyze_game_job(game_id: int, redis) -> dict:
    """Тело arq-задачи analyze_game: SF-факты + классификация (без LLM).

    Пошаговые eval'ы: каждая позиция (N+1) анализируется профилем
    `analysis` (короткий movetime), delta по методу annotator
    (eval_before/eval_after с точки зрения ходившего). Прогресс — Redis
    pubsub `chess:progress:{game_id}` (SSE).
    """
    from core.db import session_factory
    from engine.service import EngineService, white_cp

    async def publish(payload: dict) -> None:
        try:
            asyncio.get_running_loop()
            await redis.publish(progress_channel(game_id), json.dumps(payload))
        except Exception:  # noqa: BLE001 — прогресс не критичен
            pass

    async with session_factory() as session:
        game = await session.get(ChessGame, game_id)
        if game is None:
            return {"error": "game not found"}
        analysis = (
            await session.execute(
                select(ChessAnalysis).where(ChessAnalysis.game_id == game_id)
            )
        ).scalar_one_or_none()
        if analysis is None:
            return {"error": "analysis row not found"}
        analysis.status = AnalysisStatus.RUNNING
        await session.commit()

        try:
            parsed = parse_pgn(game.pgn)
            board = chess.Board(parsed.initial_fen)
            boards = [board.copy()]
            played_uci: list[str] = []
            for move_rec in parsed.moves:
                move = board.parse_san(move_rec.san)
                board.push(move)
                played_uci.append(move.uci())
                boards.append(board.copy())

            lines_by_position: list[list[EngineLine]] = []
            total_positions = len(boards)
            async with EngineService() as engine:
                for index, position in enumerate(boards):
                    if _terminal_score(position) is not None:
                        lines_by_position.append([])  # терминальная — движок не зовём
                        continue
                    lines = await engine.analyze(
                        position.fen(), "analysis", interactive=False
                    )
                    lines_by_position.append(lines)
                    if index % 5 == 0 or index == total_positions - 1:
                        await publish(
                            {"ply": index, "total": total_positions, "status": "running"}
                        )

            white_scores: list[int] = []
            for i, position in enumerate(boards):
                terminal = _terminal_score(position)
                if terminal is not None:
                    white_scores.append(terminal)
                else:
                    white_scores.append(white_cp(lines_by_position[i][0], position.turn))
            move_analyses: list[dict] = []
            for index, move_rec in enumerate(parsed.moves, start=1):
                mover_sign = 1 if boards[index - 1].turn == chess.WHITE else -1
                eval_before = white_scores[index - 1] * mover_sign
                eval_after = white_scores[index] * mover_sign
                delta = max(0, eval_before - eval_after)
                is_best = played_uci[index - 1] == lines_by_position[index - 1][0].move_uci
                move_analyses.append(
                    {
                        "ply": move_rec.ply,
                        "fenBefore": boards[index - 1].fen(),
                        "playedSan": move_rec.san,
                        "playedUci": played_uci[index - 1],
                        "bestSan": _san_of(
                            boards[index - 1],
                            lines_by_position[index - 1][0].move_uci,
                        ),
                        "bestUci": lines_by_position[index - 1][0].move_uci,
                        "evalBefore": eval_before,
                        "deltaCp": delta,
                        "classification": classify_move(delta, is_best=is_best),
                    }
                )

            blunders = [m for m in move_analyses if m["classification"] == "blunder"]
            analysis.sf = {
                "moves": move_analyses,
                "blunders": blunders,
                "summary": {
                    "plyCount": len(move_analyses),
                    "blunderCount": len(blunders),
                    "white": parsed.white,
                    "black": parsed.black,
                },
            }
            analysis.status = AnalysisStatus.DONE
            await session.commit()
            await publish({"status": "done", "blunderCount": len(blunders)})
            return {"ok": True, "blunders": len(blunders)}
        except Exception as exc:  # noqa: BLE001 — фиксируем статус failed
            logger.exception("chess: analyze_game %s упал", game_id)
            analysis.status = AnalysisStatus.FAILED
            analysis.sf = {"error": str(exc)}
            await session.commit()
            await publish({"status": "failed"})
            return {"error": str(exc)}

