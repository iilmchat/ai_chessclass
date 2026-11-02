"""S-52: API повторения — очередь, карточки, SM-2 ответы, статистика."""

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import Field

from core.base import CamelModel
from domains.auth.deps import CurrentUser, DbSession
from domains.review import service as svc
from domains.review.models import ReviewCard

router = APIRouter(prefix="/review", tags=["review"])


class CardOut(CamelModel):
    id: str
    source_type: str
    source_ref: str | None
    front: str
    back: str
    ease: float
    interval_days: int
    repetitions: int
    lapses: int
    due_at: datetime
    suspended: bool


class QueueOut(CamelModel):
    cards: list[CardOut]
    due_count: int
    daily_limit: int


class CardCreateIn(CamelModel):
    front: str = Field(min_length=3, max_length=4000)
    back: str = Field(min_length=1, max_length=4000)


class AnswerIn(CamelModel):
    rating: str = Field(pattern=r"^(again|hard|good|easy)$")


class StatsOut(CamelModel):
    total: int
    due: int
    reviews_today: int
    retention: float | None
    daily_limit: int
    sm2: dict


def _out(card: ReviewCard) -> CardOut:
    return CardOut(
        id=str(card.id),
        source_type=card.source_type,
        source_ref=card.source_ref,
        front=card.front,
        back=card.back,
        ease=float(card.ease),
        interval_days=card.interval_days,
        repetitions=card.repetitions,
        lapses=card.lapses,
        due_at=card.due_at,
        suspended=card.suspended,
    )


@router.get("/queue", response_model=QueueOut)
async def get_queue(
    user: CurrentUser,
    session: DbSession,
    limit: int | None = Query(default=None, ge=1, le=100),
) -> QueueOut:
    cards, due = await svc.queue(session, user.id, limit)
    from core.config import settings

    return QueueOut(
        cards=[_out(card) for card in cards],
        due_count=due,
        daily_limit=settings.review_daily_limit,
    )


@router.post("/cards", status_code=201, response_model=CardOut)
async def create_card(
    body: CardCreateIn, user: CurrentUser, session: DbSession
) -> CardOut:
    card = await svc.create_card(
        session,
        user.id,
        front=body.front,
        back=body.back,
    )
    await session.commit()
    return _out(card)


@router.post("/cards/{card_id}/answer", response_model=CardOut)
async def answer(
    card_id: int, body: AnswerIn, user: CurrentUser, session: DbSession
) -> CardOut:
    card = await svc.answer(session, user.id, card_id, body.rating)
    await session.commit()
    return _out(card)


@router.get("/stats", response_model=StatsOut)
async def stats(user: CurrentUser, session: DbSession) -> StatsOut:
    return StatsOut(**await svc.stats(session, user.id))
