"""Когнитивный сервис: пересчёт недельных EMA (§10.3) и срезы для API.

score = clamp(50 + Σ весов за неделю × k, 0, 100), где 50 — «нейтрально»;
EMA сглаживает между неделями: score_new = α·raw + (1−α)·score_prev.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from domains.cognitive.models import Skill, SkillEvent, UserSkillScore

logger = logging.getLogger(__name__)

#: базовый «нейтральный» скор и масштаб перевода весов в 0..100
BASE_SCORE = Decimal("50")
WEIGHT_SCALE = Decimal("10")
SCORE_MIN = Decimal("0")
SCORE_MAX = Decimal("100")


def iso_week(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


async def recalc_user_scores(
    session: AsyncSession, user_id: int, *, weeks: int = 4
) -> int:
    """Пересчитать EMA-скоры пользователя за последние `weeks` недель.

    Использует события (weight/occurred_at); отсутствие событий — скор
    сохраняет предыдущее значение (не сбрасывается). Возвращает число
    обновлённых строк.
    """
    today = date.today()
    updated = 0
    prev_scores = {
        (s.skill_id): s.score
        for s in (
            await session.execute(
                select(UserSkillScore).where(UserSkillScore.user_id == user_id)
            )
        ).scalars()
    }
    events = (
        await session.execute(
            select(SkillEvent).where(SkillEvent.user_id == user_id)
        )
    ).scalars().all()
    by_skill_week: dict[tuple[int, str], Decimal] = {}
    for event in events:
        key = (event.skill_id, iso_week(event.occurred_at.date()))
        by_skill_week[key] = by_skill_week.get(key, Decimal("0")) + event.weight

    for back in range(weeks - 1, -1, -1):
        week_start = today - timedelta(days=7 * back)
        week = iso_week(week_start)
        for skill in (
            await session.execute(select(Skill))
        ).scalars():
            raw = by_skill_week.get((skill.id, week), Decimal("0"))
            raw_score = BASE_SCORE + raw * WEIGHT_SCALE
            raw_score = max(SCORE_MIN, min(SCORE_MAX, raw_score))
            prev = prev_scores.get(skill.id, BASE_SCORE)
            alpha = Decimal(str(settings.skill_ema_alpha))
            score = (alpha * raw_score + (Decimal("1") - alpha) * prev).quantize(
                Decimal("0.01")
            )
            existing = await session.get(UserSkillScore, (user_id, skill.id))
            if existing is None:
                session.add(
                    UserSkillScore(
                        user_id=user_id, skill_id=skill.id, week=week, score=score
                    )
                )
                updated += 1
            else:
                existing.week = week
                existing.score = score
                updated += 1
    await session.flush()
    return updated


async def scores_snapshot(
    session: AsyncSession, user_id: int
) -> list[dict]:
    """Срез навыков для дашборда: slug/название/домен/скор/тренд (Δ к прошлой неделе)."""
    rows = (
        await session.execute(
            select(Skill, UserSkillScore)
            .outerjoin(
                UserSkillScore,
                (UserSkillScore.skill_id == Skill.id)
                & (UserSkillScore.user_id == user_id),
            )
            .order_by(Skill.id)
        )
    ).all()
    snapshot: list[dict] = []
    for skill, score in rows:
        value = float(score.score) if score is not None else 50.0
        snapshot.append(
            {
                "slug": skill.slug,
                "titleRu": skill.title_ru,
                "domain": skill.domain.value,
                "score": round(value, 1),
                "week": score.week if score is not None else None,
            }
        )
    return snapshot


async def recommendations(
    session: AsyncSession, user_id: int, limit: int = 3
) -> list[dict]:
    """Рекомендации по skill_links (§10.4): если навык A отстаёт (<40),
    предложить связанный B-навык (тренировки)."""
    scores = {
        s.skill_id: float(s.score)
        for s in (
            await session.execute(
                select(UserSkillScore).where(UserSkillScore.user_id == user_id)
            )
        ).scalars()
    }
    from domains.cognitive.models import SkillLink

    links = (
        await session.execute(
            select(SkillLink, Skill, Skill)
            .join(Skill, Skill.id == SkillLink.from_skill_id)
            .order_by(SkillLink.id)
        )
    ).all()
    out: list[dict] = []
    for _link, from_skill, to_skill in links:
        weak = scores.get(from_skill.id, 50.0) < 40
        if weak:
            out.append(
                {
                    "fromSkill": from_skill.slug,
                    "fromTitle": from_skill.title_ru,
                    "toSkill": to_skill.slug,
                    "toTitle": to_skill.title_ru,
                    "hint": (
                        f"«{to_skill.title_ru}»: тренировки по этой теме помогут, "
                        f"пока «{from_skill.title_ru}» отстаёт."
                    ),
                }
            )
        if len(out) >= limit:
            break
    return out
