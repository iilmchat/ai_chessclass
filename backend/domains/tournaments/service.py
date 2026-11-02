"""S-45: турниры ботов (bracket/round-robin) без LLM."""

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import chess
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from domains.audit import service as audit_svc
from domains.auth.models import User
from domains.bot_lab.models import BotVersion
from domains.bot_lab.runner import run_bot_move
from domains.tournaments.models import (
    Tournament,
    TournamentMatch,
    TournamentParticipant,
)

logger = logging.getLogger(__name__)

MatchRunner = Callable[
    [BotVersion, BotVersion], Awaitable[tuple[str, int, int]]
]


async def _default_match(
    bot_a: BotVersion, bot_b: BotVersion
) -> tuple[str, int, int]:
    """Партия двух ботов в песочнице; без LLM и без Elo."""
    started = time.perf_counter()
    board = chess.Board()
    ply = 0
    while not board.is_game_over() and ply < settings.tournament_max_plies:
        bot = bot_a if board.turn == chess.WHITE else bot_b
        move_result = await run_bot_move(
            bot.code,
            bot.entry,
            board.fen(),
            timeout_s=settings.bot_permove_timeout_s,
            memory_limit_mb=settings.sandbox_memory_limit_mb,
            max_output_chars=settings.sandbox_max_output_chars,
        )
        if not move_result["ok"]:
            winner = "b" if board.turn == chess.WHITE else "a"
            return winner, ply + 1, int((time.perf_counter() - started) * 1000)
        board.push(chess.Move.from_uci(move_result["moveUci"]))
        ply += 1
    outcome = board.outcome()
    if outcome is not None and outcome.winner is not None:
        result = "a" if outcome.winner == chess.WHITE else "b"
    else:
        result = "draw"
    return result, ply, int((time.perf_counter() - started) * 1000)


def _winner(
    result: str, bot_a: BotVersion, bot_b: BotVersion
) -> BotVersion | None:
    if result == "a":
        return bot_a
    if result == "b":
        return bot_b
    # ничья в плей-офф: проходит меньший seed/id (детерминированно)
    return bot_a if bot_a.id < bot_b.id else bot_b


def _apply_result(
    participants: dict[int, TournamentParticipant],
    bot_a: BotVersion,
    bot_b: BotVersion,
    result: str,
) -> None:
    pa = participants[bot_a.id]
    pb = participants[bot_b.id]
    if result == "a":
        pa.wins += 1
        pb.losses += 1
        pa.points += 3
    elif result == "b":
        pb.wins += 1
        pa.losses += 1
        pb.points += 3
    else:
        pa.draws += 1
        pb.draws += 1
        pa.points += 1
        pb.points += 1


async def run_tournament(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    format: str,
    bot_ids: list[int],
    match_runner: MatchRunner | None = None,
) -> Tournament:
    if format not in ("bracket", "round_robin"):
        raise AppError("tournament_format_invalid", "Неизвестный формат", 422)
    if not 2 <= len(bot_ids) <= 16 or len(set(bot_ids)) != len(bot_ids):
        raise AppError(
            "tournament_participants_invalid",
            "Нужно 2–16 уникальных ботов",
            422,
        )
    bots = (
        await session.execute(
            select(BotVersion).where(
                BotVersion.id.in_(bot_ids),
                BotVersion.is_active.is_(True),
            )
        )
    ).scalars().all()
    if len(bots) != len(bot_ids):
        raise AppError("tournament_bots_not_found", "Часть ботов не найдена", 404)
    order = {bot_id: index for index, bot_id in enumerate(bot_ids)}
    bots = sorted(bots, key=lambda bot: order[bot.id])

    tournament = Tournament(
        name=name.strip(),
        format=format,
        status="running",
        created_by=user.id,
        started_at=datetime.now(UTC),
        meta={"participants": len(bots)},
    )
    session.add(tournament)
    await session.flush()

    participants: dict[int, TournamentParticipant] = {}
    for seed, bot in enumerate(bots, start=1):
        participant = TournamentParticipant(
            tournament_id=tournament.id,
            bot_version_id=bot.id,
            user_id=bot.user_id,
            seed=seed,
        )
        session.add(participant)
        participants[bot.id] = participant
    await session.flush()

    runner = match_runner or _default_match
    match_no = 0

    if format == "bracket":
        current = bots
        round_no = 1
        while len(current) > 1:
            next_round: list[BotVersion] = []
            for index in range(0, len(current), 2):
                bot_a = current[index]
                bot_b = current[index + 1] if index + 1 < len(current) else None
                if bot_b is None:
                    next_round.append(bot_a)
                    continue
                result, moves, duration = await runner(bot_a, bot_b)
                winner = _winner(result, bot_a, bot_b)
                assert winner is not None
                match_no += 1
                session.add(
                    TournamentMatch(
                        tournament_id=tournament.id,
                        round_no=round_no,
                        match_no=match_no,
                        bot_a_id=bot_a.id,
                        bot_b_id=bot_b.id,
                        winner_id=winner.id,
                        result=result,
                        moves_count=moves,
                        duration_ms=duration,
                    )
                )
                _apply_result(participants, bot_a, bot_b, result)
                next_round.append(winner)
            current = next_round
            round_no += 1
    else:
        round_no = 1
        for i, bot_a in enumerate(bots):
            for bot_b in bots[i + 1 :]:
                result, moves, duration = await runner(bot_a, bot_b)
                match_no += 1
                winner = _winner(result, bot_a, bot_b) if result != "draw" else None
                session.add(
                    TournamentMatch(
                        tournament_id=tournament.id,
                        round_no=round_no,
                        match_no=match_no,
                        bot_a_id=bot_a.id,
                        bot_b_id=bot_b.id,
                        winner_id=winner.id if winner is not None else None,
                        result=result,
                        moves_count=moves,
                        duration_ms=duration,
                    )
                )
                _apply_result(participants, bot_a, bot_b, result)

    ranked = sorted(
        participants.values(),
        key=lambda p: (-p.points, -p.wins, p.seed),
    )
    for rank, participant in enumerate(ranked, start=1):
        participant.rank = rank
    tournament.status = "done"
    tournament.finished_at = datetime.now(UTC)
    tournament.meta = {
        "participants": len(bots),
        "matches": match_no,
        "format": format,
    }
    await session.flush()
    await audit_svc.record(
        session,
        user,
        "tournaments.run",
        target_type="tournament",
        target_id=tournament.id,
        meta={"format": format, "participants": len(bots), "matches": match_no},
    )
    return tournament


async def list_tournaments(session: AsyncSession) -> list[Tournament]:
    return list(
        (
            await session.execute(
                select(Tournament).order_by(Tournament.id.desc())
            )
        ).scalars()
    )


async def get_tournament(
    session: AsyncSession, tournament_id: int
) -> tuple[Tournament, list[TournamentParticipant], list[TournamentMatch]]:
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise AppError("tournament_not_found", "Турнир не найден", 404)
    participants = list(
        (
            await session.execute(
                select(TournamentParticipant)
                .where(TournamentParticipant.tournament_id == tournament_id)
                .order_by(TournamentParticipant.rank, TournamentParticipant.seed)
            )
        ).scalars()
    )
    matches = list(
        (
            await session.execute(
                select(TournamentMatch)
                .where(TournamentMatch.tournament_id == tournament_id)
                .order_by(TournamentMatch.round_no, TournamentMatch.match_no)
            )
        ).scalars()
    )
    return tournament, participants, matches
