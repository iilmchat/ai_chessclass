"""Запись флагов (заготовка S-09; просмотр/ревью — дашборд учителя E-08+)."""

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from domains.anticheat.models import AnticheatFlag, FlagDomain, FlagKind, FlagStatus

logger = logging.getLogger(__name__)

#: эвристика low_effort: ≤ LOW_EFFORT_MAX_LINES содержательных строк
LOW_EFFORT_MAX_LINES = 3


async def record_flag(
    session: AsyncSession,
    *,
    user_id: int,
    kind: FlagKind,
    domain: FlagDomain,
    confidence: Decimal,
    evidence: dict[str, Any],
    source_ref: str | None = None,
) -> AnticheatFlag | None:
    """Флаги не блокируют ничего — только фиксируются (§9.1)."""
    flag = AnticheatFlag(
        user_id=user_id,
        kind=kind,
        domain=domain,
        source_ref=source_ref,
        confidence=confidence,
        evidence=evidence,
        status=FlagStatus.NEW,
    )
    session.add(flag)
    await session.flush()
    logger.info(
        "anticheat: флаг %s user_id=%s confidence=%s", kind.value, user_id, confidence
    )
    return flag


def _code_lines(code: str) -> int:
    """Число содержательных строк (без пустых и комментариев)."""
    return sum(
        1
        for line in code.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


async def check_low_effort(
    session: AsyncSession,
    *,
    user_id: int,
    submission_id: int,
    code: str,
    starter_code: str,
    attempt_no: int,
) -> AnticheatFlag | None:
    """Эвристика low_effort (§9.2): копипаста starter'а при повторных попытках
    или ~3 содержательные строки."""
    evidence: dict[str, Any] = {
        "submissionId": submission_id,
        "codeLines": _code_lines(code),
        "attemptNo": attempt_no,
    }
    reasons: list[str] = []
    confidence = Decimal("0.00")
    if attempt_no > 1 and code.strip() == starter_code.strip() and starter_code.strip():
        reasons.append("starter_unchanged_repeat")
        confidence = max(confidence, Decimal("0.80"))
    if _code_lines(code) <= LOW_EFFORT_MAX_LINES:
        reasons.append("tiny_code")
        confidence = max(confidence, Decimal("0.60"))
    if not reasons:
        return None
    evidence["reasons"] = reasons
    return await record_flag(
        session,
        user_id=user_id,
        kind=FlagKind.LOW_EFFORT,
        domain=FlagDomain.PYTHON,
        confidence=confidence,
        evidence=evidence,
        source_ref=f"py_submission:{submission_id}",
    )
