"""S-52: SM-2 карточки, очередь повторений и интеграции с ошибками."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from domains.review.models import ReviewCard, ReviewEvent

QUALITY = {"again": 0, "hard": 3, "good": 4, "easy": 5}
RATINGS = tuple(QUALITY)


def sm2(
    *, ease: float, interval_days: int, repetitions: int, quality: int
) -> tuple[float, int, int, int]:
    """Вернуть (ease, interval, repetitions, lapses_delta) по SM-2."""
    if quality < 3:
        return max(1.3, round(ease - 0.2, 2)), 1, 0, 1
    new_ease = ease + (
        0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    )
    new_ease = max(1.3, round(new_ease, 2))
    if repetitions == 0:
        interval = 1
    elif repetitions == 1:
        interval = 6
    else:
        interval = max(1, round(interval_days * new_ease))
    return new_ease, interval, repetitions + 1, 0


async def create_card(
    session: AsyncSession,
    user_id: int,
    *,
    front: str,
    back: str,
    source_type: str = "manual",
    source_ref: str | None = None,
) -> ReviewCard:
    if source_type not in ("manual", "python", "chess"):
        raise AppError("review_source_invalid", "Неизвестный тип карточки", 422)
    if source_ref is not None:
        existing = (
            await session.execute(
                select(ReviewCard).where(
                    ReviewCard.user_id == user_id,
                    ReviewCard.source_type == source_type,
                    ReviewCard.source_ref == source_ref,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
    card = ReviewCard(
        user_id=user_id,
        source_type=source_type,
        source_ref=source_ref,
        front=front.strip()[:4000],
        back=back.strip()[:4000],
        ease=Decimal("2.50"),
        interval_days=0,
        repetitions=0,
        due_at=datetime.now(UTC),
    )
    session.add(card)
    await session.flush()
    return card


async def create_from_python(
    session: AsyncSession,
    user_id: int,
    *,
    assignment_id: int,
    assignment_title: str,
    topic: str,
    failed_test: int | None,
) -> ReviewCard:
    test_hint = f" Тест №{failed_test}." if failed_test is not None else ""
    return await create_card(
        session,
        user_id,
        source_type="python",
        source_ref=f"py:{assignment_id}",
        front=f"Python: {assignment_title} ({topic}).{test_hint} Что нужно исправить?",
        back=(
            "Проверьте условие/граничные случаи и повторите тему; "
            "откройте тест и сравните ожидаемый вывод."
        ),
    )


async def create_from_chess(
    session: AsyncSession,
    user_id: int,
    *,
    game_id: int,
    ply: int,
    fen: str,
    best_san: str,
    played_san: str,
) -> ReviewCard:
    return await create_card(
        session,
        user_id,
        source_type="chess",
        source_ref=f"chess:{game_id}:{ply}",
        front=f"Шахматы, ход {ply}: {fen}\nСыграно: {played_san}. Найдите лучший ход.",
        back=f"Лучший ход: {best_san}",
    )


async def get_card(session: AsyncSession, user_id: int, card_id: int) -> ReviewCard:
    card = await session.get(ReviewCard, card_id)
    if card is None or card.user_id != user_id:
        raise AppError("review_card_not_found", "Карточка не найдена", 404)
    return card


async def queue(
    session: AsyncSession, user_id: int, limit: int | None = None
) -> tuple[list[ReviewCard], int]:
    now = datetime.now(UTC)
    cap = min(limit or settings.review_daily_limit, settings.review_daily_limit)
    due_count = int(
        await session.scalar(
            select(func.count())
            .select_from(ReviewCard)
            .where(
                ReviewCard.user_id == user_id,
                ReviewCard.suspended.is_(False),
                ReviewCard.due_at <= now,
            )
        )
        or 0
    )
    cards = list(
        (
            await session.execute(
                select(ReviewCard)
                .where(
                    ReviewCard.user_id == user_id,
                    ReviewCard.suspended.is_(False),
                    ReviewCard.due_at <= now,
                )
                .order_by(ReviewCard.due_at, ReviewCard.id)
                .limit(cap)
            )
        ).scalars()
    )
    return cards, due_count


async def answer(
    session: AsyncSession, user_id: int, card_id: int, rating: str
) -> ReviewCard:
    if rating not in QUALITY:
        raise AppError(
            "review_rating_invalid", "rating: again | hard | good | easy", 422
        )
    card = await get_card(session, user_id, card_id)
    before = card.interval_days
    quality = QUALITY[rating]
    ease, interval, repetitions, lapse_delta = sm2(
        ease=float(card.ease),
        interval_days=card.interval_days,
        repetitions=card.repetitions,
        quality=quality,
    )
    card.ease = Decimal(str(ease))
    card.interval_days = interval
    card.repetitions = repetitions
    card.lapses += lapse_delta
    card.due_at = datetime.now(UTC) + timedelta(days=interval)
    session.add(
        ReviewEvent(
            card_id=card.id,
            user_id=user_id,
            rating=rating,
            quality=quality,
            interval_before=before,
            interval_after=interval,
            ease_after=Decimal(str(ease)),
        )
    )
    await session.flush()
    return card


async def stats(session: AsyncSession, user_id: int) -> dict:
    now = datetime.now(UTC)
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(ReviewCard)
            .where(ReviewCard.user_id == user_id)
        )
        or 0
    )
    due = int(
        await session.scalar(
            select(func.count())
            .select_from(ReviewCard)
            .where(
                ReviewCard.user_id == user_id,
                ReviewCard.suspended.is_(False),
                ReviewCard.due_at <= now,
            )
        )
        or 0
    )
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    reviews_today = int(
        await session.scalar(
            select(func.count())
            .select_from(ReviewEvent)
            .where(
                ReviewEvent.user_id == user_id,
                ReviewEvent.created_at >= today,
            )
        )
        or 0
    )
    good = int(
        await session.scalar(
            select(func.count())
            .select_from(ReviewEvent)
            .where(
                ReviewEvent.user_id == user_id,
                ReviewEvent.quality >= 3,
            )
        )
        or 0
    )
    all_reviews = int(
        await session.scalar(
            select(func.count())
            .select_from(ReviewEvent)
            .where(ReviewEvent.user_id == user_id)
        )
        or 0
    )
    return {
        "total": total,
        "due": due,
        "reviewsToday": reviews_today,
        "retention": round(good / all_reviews, 3) if all_reviews else None,
        "dailyLimit": settings.review_daily_limit,
        "sm2": {"ease": 2.5, "firstInterval": 1, "secondInterval": 6},
    }
