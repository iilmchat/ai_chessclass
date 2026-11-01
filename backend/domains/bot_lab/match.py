"""Матч-луп (Design §7.2/§7.4): ученик (песочница) vs оппонент (trusted).

Без LLM (§7.3); MAX_PLIES=60, бюджет BOT_MATCH_BUDGET_S=120; нарушения
ученика = немедленное поражение; Elo K=32 clamp ±40 (ADR-008).
Оппоненты: random/greedy/minimax2 (trusted) + Stockfish UCI_Elo 1400/1600/1800.
"""

import json
import logging
import random
import time
from datetime import UTC, datetime
from decimal import Decimal

import chess

from core.config import settings
from domains.bot_lab.elo import elo_delta as compute_delta
from domains.bot_lab.opponents import OPPONENTS
from domains.bot_lab.runner import run_bot_move

logger = logging.getLogger(__name__)

MAX_PLIES = 60

#: SF-оппоненты лестницы (часть 2): имя → UCI_Elo
SF_OPPONENTS: dict[str, int] = {
    "stockfish-1400": 1400,
    "stockfish-1600": 1600,
    "stockfish-1800": 1800,
}

#: движок оппонента — фиксированный короткий movetime (§7.3)
SF_MOVE_MS = 300


async def run_match(bot_version_id: int, opponent: str, redis) -> dict:
    """Полный матч: ходы, вердикт, Elo, запись bot_matches/moves."""
    from core.db import session_factory
    from domains.bot_lab.models import (
        BotMatch,
        BotMatchMove,
        BotStats,
        BotVersion,
        MatchResult,
    )

    is_sf = opponent in SF_OPPONENTS
    if not is_sf and opponent not in OPPONENTS:
        return {"error": f"unknown opponent {opponent!r}"}
    opponent_elo = (
        SF_OPPONENTS[opponent] if is_sf else OPPONENTS[opponent][0]
    )

    started = time.perf_counter()
    async with session_factory() as session:
        version = await session.get(BotVersion, bot_version_id)
        if version is None:
            return {"error": "bot not found"}
        match = BotMatch(
            version_id=version.id,
            user_id=version.user_id,
            opponent=opponent,
            result=MatchResult.DRAW,
            moves_count=0,
            duration_ms=0,
            elo_delta=Decimal("0"),
        )
        session.add(match)
        await session.flush()

        board = chess.Board()
        result_final = MatchResult.DRAW
        ply = 0
        deadline = started + settings.bot_match_budget_s
        failure: MatchResult | None = None
        sampled_count = 0
        last_student_move = None

        sf_engine = None
        if is_sf:
            from engine.service import EngineService

            sf_engine = EngineService()
            await sf_engine.set_strength(SF_OPPONENTS[opponent])

        try:
            while not board.is_game_over() and ply < MAX_PLIES:
                if time.perf_counter() > deadline:
                    failure = MatchResult.TIMEOUT
                    break
                student_turn = board.turn == chess.WHITE
                started_move = time.perf_counter()
                if student_turn:
                    move_result = await run_bot_move(
                        version.code,
                        version.entry,
                        board.fen(),
                        timeout_s=settings.bot_permove_timeout_s,
                        memory_limit_mb=settings.sandbox_memory_limit_mb,
                        max_output_chars=settings.sandbox_max_output_chars,
                    )
                    if not move_result["ok"]:
                        # нарушение/ошибка ученика = немедленное поражение (§7.4)
                        failure = (
                            MatchResult.TIMEOUT
                            if move_result["errorType"] == "TimeoutError"
                            else MatchResult.LOSS
                        )
                        session.add(
                            BotMatchMove(
                                match_id=match.id, ply=ply + 1, fen=board.fen(),
                                uci="0000", agent="student",
                                think_ms=move_result["timeMs"],
                            )
                        )
                        ply += 1
                        break
                    move_uci = move_result["moveUci"]
                    think_ms = move_result["timeMs"]
                    agent = "student"
                    sampled = random.random() < 0.10  # 10 % — для engine_likeliness (S-22)
                else:
                    if is_sf and sf_engine is not None:
                        lines = await sf_engine.analyze(
                            board.fen(), "analysis", interactive=False
                        )
                        move_uci = lines[0].move_uci
                    else:
                        move = OPPONENTS[opponent][1](chess.Board(board.fen()))
                        move_uci = move.uci()
                    think_ms = int((time.perf_counter() - started_move) * 1000)
                    agent = "opponent"
                    sampled = False

                board.push(chess.Move.from_uci(move_uci))
                move_row = BotMatchMove(
                    match_id=match.id, ply=ply + 1, fen=board.fen(),
                    uci=move_uci, agent=agent, think_ms=think_ms,
                    sf_sample=sampled,
                )
                session.add(move_row)
                if agent == "student":
                    last_student_move = move_row
                    if sampled:
                        sampled_count += 1
                ply += 1

            if failure is not None:
                result_final = failure
            elif last_student_move is not None and sampled_count == 0:
                last_student_move.sf_sample = True  # хотя бы один семпл за матч
            elif board.is_game_over():
                outcome = board.outcome()
                if outcome is None or outcome.winner is None:
                    result_final = MatchResult.DRAW
                else:
                    result_final = (
                        MatchResult.WIN
                        if outcome.winner == chess.WHITE
                        else MatchResult.LOSS
                    )
            else:
                result_final = MatchResult.DRAW  # MAX_PLIES исчерпан

            stats = await session.get(BotStats, version.user_id)
            if stats is None:
                stats = BotStats(user_id=version.user_id)
                session.add(stats)
                await session.flush()
            delta = compute_delta(
                stats.elo, Decimal(str(opponent_elo)), result_final.value
            )
            stats.elo = (stats.elo + delta).quantize(Decimal("0.1"))
            if result_final is MatchResult.WIN:
                stats.wins += 1
            elif result_final is MatchResult.LOSS:
                stats.losses += 1
            else:
                stats.draws += 1

            match.result = result_final
            match.moves_count = ply
            match.duration_ms = int((time.perf_counter() - started) * 1000)
            match.elo_delta = delta
            match.finished_at = datetime.now(UTC)
            await session.commit()

            logger.info(
                "bots: матч %s vs %s → %s (%d ходов, Δelo %s)",
                bot_version_id, opponent, result_final.value, ply, delta,
            )
            try:
                await redis.publish(
                    f"bots:match:{match.id}",
                    json.dumps(
                        {
                            "status": "done",
                            "result": result_final.value,
                            "eloDelta": float(delta),
                        }
                    ),
                )
            except Exception:  # noqa: BLE001
                pass

            return {
                "matchId": match.id,
                "result": result_final.value,
                "plies": ply,
                "eloDelta": float(delta),
                "elo": float(stats.elo),
            }
        finally:
            if sf_engine is not None:
                await sf_engine.aclose()
