"""S-42: прогресс Python, стрики и достижения.

Стрик: +1 за первый решённый ассайнмент в новый день; повторное решение
того же задания не двигает стрик. Пропуск дня сбрасывает текущий стрик в 1.
Бейдж выдаётся один раз (PK user_id+achievement_id).
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from domains.audit import service as audit_svc
from domains.auth.models import User
from domains.progress.models import Achievement, PyProgress, UserAchievement


async def _get_or_create(session: AsyncSession, user_id: int) -> PyProgress:
    progress = await session.get(PyProgress, user_id)
    if progress is None:
        progress = PyProgress(user_id=user_id)
        session.add(progress)
        await session.flush()
    return progress


async def _award_achievements(
    session: AsyncSession,
    user: User,
    progress: PyProgress,
    *,
    request: Request | None,
) -> list[Achievement]:
    catalog = (
        await session.execute(select(Achievement).order_by(Achievement.id))
    ).scalars().all()
    awarded_ids = set(
        (
            await session.execute(
                select(UserAchievement.achievement_id).where(
                    UserAchievement.user_id == user.id
                )
            )
        ).scalars()
    )
    topic_count = sum(
        1 for value in (progress.topics or {}).values() if int(value) > 0
    )
    awards: list[Achievement] = []
    for achievement in catalog:
        if achievement.id in awarded_ids:
            continue
        qualifies = (
            (achievement.kind == "solved"
             and progress.solved_count >= achievement.threshold)
            or (achievement.kind == "streak"
                and progress.longest_streak >= achievement.threshold)
            or (achievement.kind == "topics"
                and topic_count >= achievement.threshold)
        )
        if not qualifies:
            continue
        session.add(
            UserAchievement(
                user_id=user.id,
                achievement_id=achievement.id,
                context={
                    "solvedCount": progress.solved_count,
                    "longestStreak": progress.longest_streak,
                    "topics": topic_count,
                },
            )
        )
        await session.flush()
        await audit_svc.record(
            session,
            user,
            "achievements.award",
            target_type="achievement",
            target_id=achievement.id,
            source="system",
            meta={"code": achievement.code},
            request=request,
        )
        awards.append(achievement)
    return awards


async def record_passed_solution(
    session: AsyncSession,
    user: User,
    topic: str,
    assignment_id: int,
    *,
    today: date | None = None,
    request: Request | None = None,
) -> tuple[PyProgress, list[Achievement]]:
    """Обновить прогресс после первого passed-решения задания."""
    progress = await _get_or_create(session, user.id)
    solved_ids = {int(value) for value in (progress.solved_assignments or [])}
    if int(assignment_id) in solved_ids:
        return progress, []

    progress.solved_assignments = [*solved_ids, int(assignment_id)]
    progress.solved_count = int(progress.solved_count or 0) + 1
    topics = dict(progress.topics or {})
    topics[topic] = int(topics.get(topic, 0)) + 1
    progress.topics = topics

    day = today or datetime.now(UTC).date()
    last = progress.last_solved_on
    if last == day:
        current = max(int(progress.current_streak or 0), 1)
    elif last == day - timedelta(days=1):
        current = int(progress.current_streak or 0) + 1
    else:
        current = 1
    progress.current_streak = current
    progress.longest_streak = max(int(progress.longest_streak or 0), current)
    progress.last_solved_on = day
    await session.flush()

    awards = await _award_achievements(
        session, user, progress, request=request
    )
    return progress, awards


async def get_progress(session: AsyncSession, user_id: int) -> dict:
    progress = await session.get(PyProgress, user_id)
    catalog = (
        await session.execute(select(Achievement).order_by(Achievement.id))
    ).scalars().all()
    awarded = {
        int(row.achievement_id): row.awarded_at
        for row in (
            await session.execute(
                select(UserAchievement).where(UserAchievement.user_id == user_id)
            )
        ).scalars()
    }
    return {
        "userId": str(user_id),
        "solvedCount": int(progress.solved_count) if progress else 0,
        "topics": progress.topics if progress else {},
        "currentStreak": int(progress.current_streak) if progress else 0,
        "longestStreak": int(progress.longest_streak) if progress else 0,
        "lastSolvedOn": progress.last_solved_on if progress else None,
        "achievements": [
            {
                "code": achievement.code,
                "titleRu": achievement.title_ru,
                "description": achievement.description,
                "icon": achievement.icon,
                "awarded": achievement.id in awarded,
                "awardedAt": awarded.get(achievement.id),
            }
            for achievement in catalog
        ],
    }
