"""Детект trivial_bot (Design §9.2, S-21): тривиальный бот получает флаг.

Эвристики (пороги — config):
- короткий код (< BOT_TRIVIAL_MIN_LINES содержательных строк);
- «ходы из кармана» — код содержит захардкоженные UCI-ходы вне legal_moves;
- повторяющийся паттерн против random — один и тот же ход в одинаковых
  позициях (эвристика по истории матчей, заготовка).
Флаг не блокирует ничего (§9.1, ADR-005) — решает учитель.
"""

import logging
import re
from decimal import Decimal
from typing import Any

from domains.anticheat.models import FlagDomain, FlagKind
from domains.anticheat.service import record_flag

logger = logging.getLogger(__name__)

UCI_PATTERN = re.compile(r"[a-h][1-8][a-h][1-8]")


def _code_lines(code: str) -> int:
    """Содержательные строки (без пустых, комментариев, import)."""
    return sum(
        1
        for line in code.splitlines()
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith(("import ", "from "))
    )


def analyze_trivial(code: str, matches_played: int) -> tuple[Decimal, dict[str, Any]] | None:
    """Вернуть (confidence, evidence) или None (бот не тривиален).

    Ключевой признак — захардкоженные UCI-ходы («ходы из кармана»);
    короткий код сам по себе НЕ флаг (minimal random-бот из туториала
    валиден) — только усиливает вместе с ходами из кармана.
    """
    reasons: list[str] = []
    confidence = Decimal("0.00")

    lines = _code_lines(code)
    hardcoded = [m.group(0) for m in UCI_PATTERN.finditer(code)]
    if hardcoded:
        reasons.append("hardcoded_moves")
        confidence = max(confidence, Decimal("0.80"))
        if lines <= settings.bot_trivial_min_lines:
            reasons.append("short_code")
            confidence = max(confidence, Decimal("0.90"))

    if matches_played >= 3 and reasons:
        reasons.append("repeating_pattern_vs_random")
        confidence = max(confidence, Decimal("0.60"))

    if not reasons:
        return None
    evidence: dict[str, Any] = {
        "reasons": reasons,
        "codeLines": lines,
        "hardcodedMoves": hardcoded[:10],
        "matchesPlayed": matches_played,
    }
    return confidence, evidence


async def check_trivial_bot(
    session, user_id: int, bot_version_id: int, code: str
) -> None:
    """Заготовка S-21: записать флаг trivial_bot, если бот тривиален."""
    from sqlalchemy import func, select

    from domains.bot_lab.models import BotVersion

    matches_played = int(
        (
            await session.execute(
                select(func.count())
                .select_from(BotVersion)
                .where(BotVersion.user_id == user_id)
            )
        ).scalar_one()
    )
    verdict = analyze_trivial(code, matches_played)
    if verdict is None:
        return
    confidence, evidence = verdict
    evidence["botVersionId"] = bot_version_id
    await record_flag(
        session,
        user_id=user_id,
        kind=FlagKind.TRIVIAL_BOT,
        domain=FlagDomain.BOT,
        confidence=confidence,
        evidence=evidence,
        source_ref=f"bot_version:{bot_version_id}",
    )


from core.config import settings  # noqa: E402 — внизу для читаемости импортов выше
