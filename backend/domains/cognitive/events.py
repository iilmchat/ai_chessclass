"""События навыков (Design §10.2): emit в cognitive_skill_events.

Веса — подписаны: положительные за успехи, отрицательные за «облегчалки»
(подсказка −0.5, LLM-подсказка −1.0, открытие решения −2.0 — SPEC §8).
"""

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domains.cognitive.models import Skill, SkillDomain, SkillEvent

logger = logging.getLogger(__name__)

# базовые веса S-09 (таблица — SPEC §8)
WEIGHT_HINT_SEEDED = Decimal("-0.500")
WEIGHT_HINT_LLM = Decimal("-1.000")
WEIGHT_SOLUTION_OPEN = Decimal("-2.000")


async def emit_skill_event(
    session: AsyncSession,
    *,
    user_id: int,
    skill_slug: str,
    domain: SkillDomain,
    weight: Decimal,
    meta: dict[str, Any] | None = None,
) -> bool:
    """Записать событие по slug навыка; навык отсутствует → skip + warning."""
    skill = (
        await session.execute(select(Skill).where(Skill.slug == skill_slug))
    ).scalar_one_or_none()
    if skill is None:
        logger.warning("cognitive: навык %r не найден — событие пропущено", skill_slug)
        return False
    session.add(
        SkillEvent(
            user_id=user_id,
            skill_id=skill.id,
            domain=domain,
            weight=weight,
            meta=meta or {},
        )
    )
    await session.flush()
    return True
