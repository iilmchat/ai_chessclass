"""S-45/S-48: турниры ботов — async, replay, античит и восстановление."""

import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import chess
from sqlalchemy import func, select
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
    TournamentMove,
    TournamentParticipant,
)

logger = logging.getLogger(__name__)

MatchRunner = Callable[
    [BotVersion, BotVersion], Awaitable[tuple[Any, ...]]
]


async def _default_match(
    bot_a: BotVersion, bot_b: BotVersion
) -> tuple[str, int, int, list[dict]]:
    """Партия двух ботов в песочнице; без LLM и без Elo (S-48: + moves)."""
    started = time.perf_counter()
    board = chess.Board()
    ply = 0
    moves: list[dict] = []
    while not board.is_game_over() and ply < settings.tournament_max_plies:
        is_a = board.turn == chess.WHITE
        bot = bot_a if is_a else bot_b
        move_result = await run_bot_move(
            bot.code,
            bot.entry,
            board.fen(),
            timeout_s=settings.bot_permove_timeout_s,
            memory_limit_mb=settings.sandbox_memory_limit_mb,
            max_output_chars=settings.sandbox_max_output_chars,
        )
        if not move_result["ok"]:
            winner = "b" if is_a else "a"
            return winner, ply + 1, int((time.perf_counter() - started) * 1000), moves
        move_uci = str(move_result["moveUci"])
        fen_before = board.fen()
        board.push(chess.Move.from_uci(move_uci))
        ply += 1
        moves.append(
            {
                "bot_version_id": bot.id,
                "ply": ply,
                "fen": fen_before,
                "uci": move_uci,
                "agent": "a" if is_a else "b",
                "think_ms": int(move_result["timeMs"]),
                "sf_sample": random.random() < 0.10,
            }
        )
    outcome = board.outcome()
    if outcome is not None and outcome.winner is not None:
        result = "a" if outcome.winner == chess.WHITE else "b"
    else:
        result = "draw"
    return result, ply, int((time.perf_counter() - started) * 1000), moves


def _winner(
    result: str, bot_a: BotVersion, bot_b: BotVersion
) -> BotVersion | None:
    if result == "a":
        return bot_a
    if result == "b":
        return bot_b
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


def _total_matches(format: str, count: int) -> int:
    return count - 1 if format == "bracket" else count * (count - 1) // 2


async def _publish(redis, tournament: Tournament, **extra) -> None:
    if redis is None:
        return
    payload = {
        "status": tournament.status,
        "progress": tournament.progress,
        "total": tournament.total_matches,
        **extra,
    }
    try:
        await redis.publish(
            f"tournaments:{tournament.id}", json.dumps(payload, default=str)
        )
    except Exception:  # noqa: BLE001 - progress не критичен
        pass


async def create_tournament(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    format: str,
    bot_ids: list[int],
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
                BotVersion.id.in_(bot_ids), BotVersion.is_active.is_(True)
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
        status="queued",
        created_by=user.id,
        progress=0,
        total_matches=_total_matches(format, len(bots)),
        meta={"participants": len(bots), "format": format},
    )
    session.add(tournament)
    await session.flush()
    for seed, bot in enumerate(bots, start=1):
        session.add(
            TournamentParticipant(
                tournament_id=tournament.id,
                bot_version_id=bot.id,
                user_id=bot.user_id,
                seed=seed,
            )
        )
    await session.flush()
    await audit_svc.record(
        session,
        user,
        "tournaments.create",
        target_type="tournament",
        target_id=tournament.id,
        meta={"format": format, "participants": len(bots)},
    )
    return tournament


async def _run_match(
    runner: MatchRunner, bot_a: BotVersion, bot_b: BotVersion
) -> tuple[str, int, int, list[dict]]:
    raw = await runner(bot_a, bot_b)
    if len(raw) >= 4:
        return str(raw[0]), int(raw[1]), int(raw[2]), list(raw[3])
    return str(raw[0]), int(raw[1]), int(raw[2]), []


async def _save_match(
    session: AsyncSession,
    redis,
    tournament: Tournament,
    *,
    round_no: int,
    match_no: int,
    bot_a: BotVersion,
    bot_b: BotVersion,
    result: str,
    moves_count: int,
    duration_ms: int,
    move_rows: list[dict],
    participants: dict[int, TournamentParticipant],
) -> BotVersion:
    winner = _winner(result, bot_a, bot_b)
    assert winner is not None
    match = TournamentMatch(
        tournament_id=tournament.id,
        round_no=round_no,
        match_no=match_no,
        bot_a_id=bot_a.id,
        bot_b_id=bot_b.id,
        winner_id=winner.id,
        result=result,
        moves_count=moves_count,
        duration_ms=duration_ms,
    )
    session.add(match)
    await session.flush()
    for row in move_rows:
        session.add(
            TournamentMove(
                tournament_id=tournament.id,
                match_id=match.id,
                **row,
            )
        )
    _apply_result(participants, bot_a, bot_b, result)
    tournament.progress += 1
    await session.commit()
    await _publish(
        redis,
        tournament,
        round=match.round_no,
        match=match.match_no,
        result=result,
        matchId=match.id,
    )
    return winner


async def _existing(
    session: AsyncSession,
    tournament_id: int,
    round_no: int,
    match_no: int,
) -> TournamentMatch | None:
    return (
        await session.execute(
            select(TournamentMatch).where(
                TournamentMatch.tournament_id == tournament_id,
                TournamentMatch.round_no == round_no,
                TournamentMatch.match_no == match_no,
            )
        )
    ).scalar_one_or_none()


async def _run_bracket(
    session: AsyncSession,
    redis,
    tournament: Tournament,
    bots: list[BotVersion],
    participants: dict[int, TournamentParticipant],
    runner: MatchRunner,
) -> None:
    current = bots
    round_no = 1
    match_no = 0
    while len(current) > 1:
        next_round: list[BotVersion] = []
        for index in range(0, len(current), 2):
            if tournament.cancel_requested:
                tournament.status = "cancelled"
                tournament.finished_at = datetime.now(UTC)
                await session.commit()
                await _publish(redis, tournament)
                return
            bot_a = current[index]
            if index + 1 >= len(current):
                next_round.append(bot_a)
                continue
            bot_b = current[index + 1]
            match_no += 1
            existing = await _existing(
                session, tournament.id, round_no, match_no
            )
            if existing is not None:
                winner = (
                    await session.get(BotVersion, existing.winner_id)
                    if existing.winner_id is not None
                    else _winner(existing.result, bot_a, bot_b)
                )
                assert winner is not None
                next_round.append(winner)
                continue
            result, moves, duration, move_rows = await _run_match(
                runner, bot_a, bot_b
            )
            winner = await _save_match(
                session,
                redis,
                tournament,
                round_no=round_no,
                match_no=match_no,
                bot_a=bot_a,
                bot_b=bot_b,
                result=result,
                moves_count=moves,
                duration_ms=duration,
                move_rows=move_rows,
                participants=participants,
            )
            next_round.append(winner)
        current = next_round
        round_no += 1


async def _run_round_robin(
    session: AsyncSession,
    redis,
    tournament: Tournament,
    bots: list[BotVersion],
    participants: dict[int, TournamentParticipant],
    runner: MatchRunner,
) -> None:
    match_no = 0
    for index, bot_a in enumerate(bots):
        for bot_b in bots[index + 1 :]:
            if tournament.cancel_requested:
                tournament.status = "cancelled"
                tournament.finished_at = datetime.now(UTC)
                await session.commit()
                await _publish(redis, tournament)
                return
            match_no += 1
            existing = await _existing(session, tournament.id, 1, match_no)
            if existing is not None:
                continue
            result, moves, duration, move_rows = await _run_match(
                runner, bot_a, bot_b
            )
            await _save_match(
                session,
                redis,
                tournament,
                round_no=1,
                match_no=match_no,
                bot_a=bot_a,
                bot_b=bot_b,
                result=result,
                moves_count=moves,
                duration_ms=duration,
                move_rows=move_rows,
                participants=participants,
            )


async def _finalize_pvp(session: AsyncSession, tournament_id: int) -> None:
    """Обновить PvP-комнату/рейтинг после турнира (S-51)."""
    try:
        from domains.pvp import service as pvp_svc

        await pvp_svc.finalize_tournament(session, tournament_id)
    except Exception as exc:  # noqa: BLE001 - PvP не должен ломать турнир
        logger.warning("tournaments: pvp finalize skipped: %s", exc)


async def _check_tournament_anticheat(
    session: AsyncSession, tournament_id: int
) -> None:
    """SF-семплы турнирных ходов → engine_likeliness (S-48)."""
    try:
        from decimal import Decimal

        from domains.anticheat.likeliness import sf_match_rate
        from domains.anticheat.models import FlagDomain, FlagKind
        from domains.anticheat.service import record_flag
        from engine.service import EngineService

        participants = (
            await session.execute(
                select(TournamentParticipant).where(
                    TournamentParticipant.tournament_id == tournament_id
                )
            )
        ).scalars().all()
        async with EngineService() as engine:
            for participant in participants:
                rows = (
                    await session.execute(
                        select(TournamentMove).where(
                            TournamentMove.tournament_id == tournament_id,
                            TournamentMove.bot_version_id
                            == participant.bot_version_id,
                            TournamentMove.sf_sample.is_(True),
                        )
                    )
                ).scalars().all()
                if len(rows) < 3:
                    continue
                rate = await sf_match_rate(
                    engine,
                    [{"fenBefore": row.fen, "playedUci": row.uci} for row in rows],
                )
                if rate["top1Rate"] < settings.engine_likeliness_top1_threshold:
                    continue
                await record_flag(
                    session,
                    user_id=participant.user_id,
                    kind=FlagKind.ENGINE_LIKELINESS,
                    domain=FlagDomain.BOT,
                    confidence=Decimal("0.75"),
                    evidence={
                        "tournamentId": tournament_id,
                        "botVersionId": participant.bot_version_id,
                        **rate,
                    },
                    source_ref=f"tournament:{tournament_id}",
                )
    except Exception as exc:  # noqa: BLE001 - античит не должен ломать турнир
        logger.warning("tournaments: anticheat skipped: %s", exc)


async def _run_job(
    session: AsyncSession,
    tournament_id: int,
    redis,
    match_runner: MatchRunner | None,
) -> Tournament:
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise AppError("tournament_not_found", "Турнир не найден", 404)
    if tournament.status in ("done", "cancelled"):
        return tournament
    participants = list(
        (
            await session.execute(
                select(TournamentParticipant)
                .where(TournamentParticipant.tournament_id == tournament_id)
                .order_by(TournamentParticipant.seed)
            )
        ).scalars()
    )
    if not participants:
        return tournament
    bots = list(
        (
            await session.execute(
                select(BotVersion).where(
                    BotVersion.id.in_([p.bot_version_id for p in participants])
                )
            )
        ).scalars()
    )
    order = {p.bot_version_id: p.seed for p in participants}
    bots = sorted(bots, key=lambda bot: order[bot.id])
    participants_by_bot = {p.bot_version_id: p for p in participants}
    completed = int(
        await session.scalar(
            select(func.count())
            .select_from(TournamentMatch)
            .where(TournamentMatch.tournament_id == tournament_id)
        )
        or 0
    )
    tournament.status = "running"
    tournament.progress = completed
    tournament.total_matches = tournament.total_matches or _total_matches(
        tournament.format, len(bots)
    )
    tournament.started_at = tournament.started_at or datetime.now(UTC)
    await session.commit()
    await _publish(redis, tournament)
    runner = match_runner or _default_match

    try:
        if tournament.format == "bracket":
            await _run_bracket(
                session, redis, tournament, bots, participants_by_bot, runner
            )
        else:
            await _run_round_robin(
                session, redis, tournament, bots, participants_by_bot, runner
            )
        if tournament.status == "cancelled":
            await _finalize_pvp(session, tournament_id)
            await session.commit()
            return tournament
        ranked = sorted(
            participants_by_bot.values(),
            key=lambda p: (-p.points, -p.wins, p.seed),
        )
        for rank, participant in enumerate(ranked, start=1):
            participant.rank = rank
        tournament.status = "done"
        tournament.finished_at = datetime.now(UTC)
        tournament.meta = {
            **(tournament.meta or {}),
            "matches": tournament.progress,
            "format": tournament.format,
        }
        await session.commit()
        await _check_tournament_anticheat(session, tournament_id)
        await session.commit()
        await _publish(redis, tournament)
        await _finalize_pvp(session, tournament_id)
        await session.commit()

        # S-68: teacher-событие «турнир завершён» учителям участников.
        try:
            from domains.telegram import service as telegram_svc

            for user_id in {
                p.user_id for p in participants if p.user_id is not None
            }:
                await telegram_svc.enqueue_teacher_events(
                    session,
                    child_user_id=int(user_id),
                    kind="teacher_tournament",
                    text=f"Турнир «{tournament.name}» завершён (место узнаете в ChessClass)",
                )
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("tournaments: teacher event не поставлен: %s", exc)
        return tournament
    except Exception as exc:  # noqa: BLE001
        logger.exception("tournaments: job failed id=%s", tournament_id)
        await session.rollback()
        fresh = await session.get(Tournament, tournament_id)
        if fresh is not None:
            fresh.status = "failed"
            fresh.error = str(exc)[:1000]
            fresh.finished_at = datetime.now(UTC)
            await session.commit()
            await _publish(redis, fresh)
            await _finalize_pvp(session, tournament_id)
            await session.commit()
            return fresh
        raise


async def run_tournament_job(
    tournament_id: int,
    redis=None,
    *,
    session: AsyncSession | None = None,
    match_runner: MatchRunner | None = None,
) -> Tournament:
    """Async-задача arq; идемпотентно продолжает после рестарта."""
    if session is not None:
        return await _run_job(session, tournament_id, redis, match_runner)
    from core.db import session_factory

    async with session_factory() as own_session:
        return await _run_job(own_session, tournament_id, redis, match_runner)


async def run_tournament(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    format: str,
    bot_ids: list[int],
    match_runner: MatchRunner | None = None,
) -> Tournament:
    """Синхронный wrapper для тестов/CLI; API использует enqueue."""
    tournament = await create_tournament(
        session, user, name=name, format=format, bot_ids=bot_ids
    )
    await session.commit()
    return await run_tournament_job(
        tournament.id,
        None,
        session=session,
        match_runner=match_runner,
    )


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


async def get_replay(
    session: AsyncSession, tournament_id: int, match_id: int
) -> tuple[TournamentMatch, list[TournamentMove]]:
    match = await session.get(TournamentMatch, match_id)
    if match is None or match.tournament_id != tournament_id:
        raise AppError("tournament_match_not_found", "Матч не найден", 404)
    moves = list(
        (
            await session.execute(
                select(TournamentMove)
                .where(TournamentMove.match_id == match_id)
                .order_by(TournamentMove.ply)
            )
        ).scalars()
    )
    return match, moves


async def cancel_tournament(
    session: AsyncSession, tournament_id: int, redis=None
) -> Tournament:
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise AppError("tournament_not_found", "Турнир не найден", 404)
    if tournament.status in ("done", "cancelled"):
        return tournament
    tournament.cancel_requested = True
    if tournament.status in ("draft", "queued"):
        tournament.status = "cancelled"
        tournament.finished_at = datetime.now(UTC)
    await session.commit()
    await _publish(redis, tournament)
    return tournament


async def resume_tournaments(redis) -> int:
    """Cron/startup: перезапустить queued/running после рестарта."""
    from arq.connections import RedisSettings, create_pool

    from core.db import session_factory

    async with session_factory() as session:
        ids = list(
            (
                await session.execute(
                    select(Tournament.id).where(
                        Tournament.status.in_(("queued", "running"))
                    )
                )
            ).scalars()
        )
    if not ids:
        return 0
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        for tournament_id in ids:
            await pool.enqueue_job(
                "run_tournament_job",
                tournament_id,
                _job_id=f"tournament:{tournament_id}",
            )
    finally:
        await pool.aclose()
    return len(ids)
