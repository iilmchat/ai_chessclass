"""engine_likeliness (S-22, §9.2/§9.3): ходы ученика vs топ-1/топ-3 SF.

По семплированным ходам (bot_match_moves.sf_sample) — матч rate
совпадения с топ-1/топ-3 SF и точность; превышение порога → флаг.
Пороги — config (§9.2 «пороги и метрики — параметры config»).
"""

import logging
from decimal import Decimal

import chess

from core.config import settings

logger = logging.getLogger(__name__)


async def sf_match_rate(
    engine, samples: list[dict], *, movetime_ms: int = 150
) -> dict:
    """Считать match rate ученических ходов против SF топ-1/топ-3.

    samples: [{fenBefore, playedUci}] (семплы из bot_match_moves).
    Возвращает {top1Rate, top3Rate, avgAccuracyCp, samples}.
    """
    top1 = 0
    top3 = 0
    total = 0
    deltas: list[int] = []
    for sample in samples:
        try:
            board = chess.Board(sample["fenBefore"])
            played = chess.Move.from_uci(sample["playedUci"])
        except (ValueError, KeyError):
            continue
        if played not in board.legal_moves:
            continue
        lines = await engine.analyze(
            board.fen(), "analysis", interactive=False
        )  # multipv=1 в профиле analysis — топ-1; для топ-3 нужен multipv=3
        if not lines:
            continue
        total += 1
        eval_before = _line_cp(lines[0], board.turn)
        played_move = board.parse_uci(played.uci())
        board.push(played_move)
        after_lines = await engine.analyze(
            board.fen(), "analysis", interactive=False
        )
        if after_lines:
            eval_after = _line_cp(after_lines[0], board.turn)
            deltas.append(max(0, eval_before - eval_after))
        board.pop()
        if lines[0].move_uci == sample["playedUci"]:
            top1 += 1
        if any(line.move_uci == sample["playedUci"] for line in lines[:3]):
            top3 += 1
    return {
        "top1Rate": round(top1 / total, 2) if total else 0.0,
        "top3Rate": round(top3 / total, 2) if total else 0.0,
        "avgAccuracyCp": round(sum(deltas) / len(deltas), 1) if deltas else 0.0,
        "samples": total,
    }


def _line_cp(line, turn: chess.Color) -> int:  # noqa: ANN001 — EngineLine
    if line.mate is not None:
        sign = 1 if line.mate > 0 else -1
        return sign * 9900
    return line.score_cp or 0


async def check_engine_likeliness(
    session, redis, user_id: int, bot_version_id: int, match_id: int,
    samples: list[dict] | None = None,
) -> None:
    """Порог: top1Rate ≥ 0.9 И avgAccuracy ≤ 30 cp → флаг (сильная игра +
    минимальные потери = подозрение на движок)."""
    from sqlalchemy import select

    from domains.anticheat.models import AnticheatFlag, FlagDomain, FlagKind
    from domains.bot_lab.models import BotMatchMove
    from engine.service import EngineService

    if samples is None:
        samples = [
            {
                "fenBefore": row.fen,
                "playedUci": row.uci,
            }
            for row in (
                await session.execute(
                    select(BotMatchMove).where(
                        BotMatchMove.match_id == match_id,
                        BotMatchMove.agent == "student",
                        BotMatchMove.sf_sample.is_(True),
                    )
                )
            ).scalars()
        ]
    if len(samples) < 3:  # слишком мало данных — не судим
        return

    async with EngineService() as engine:
        rate = await sf_match_rate(engine, samples)

    if rate["top1Rate"] < settings.engine_likeliness_top1_threshold:
        return
    evidence = {
        "matchId": match_id,
        "botVersionId": bot_version_id,
        **rate,
    }
    flag = AnticheatFlag(
        user_id=user_id,
        kind=FlagKind.ENGINE_LIKELINESS,
        domain=FlagDomain.BOT,
        source_ref=f"bot_match:{match_id}",
        confidence=Decimal("0.75"),
        evidence=evidence,
    )
    session.add(flag)
    await session.flush()
    logger.warning(
        "anticheat: engine_likeliness user_id=%s top1=%s",
        user_id, rate["top1Rate"],
    )
