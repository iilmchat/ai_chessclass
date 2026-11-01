"""Роутер /api/v1/bots (Design §12.2): версии ботов и тест хода."""

from fastapi import APIRouter
from pydantic import Field

from core.base import CamelModel
from domains.auth.deps import CurrentUser, DbSession
from domains.bot_lab import service as svc

router = APIRouter(prefix="/bots", tags=["bot_lab"])


class BotCreateIn(CamelModel):
    code: str = Field(min_length=10, max_length=20000)
    entry: str = Field(default="choose_move", max_length=64)


class BotOut(CamelModel):
    id: str
    versionNo: int
    entry: str
    isActive: bool
    createdAt: str


class BotTestIn(CamelModel):
    fen: str = Field(min_length=10, max_length=128)


class BotTestOut(CamelModel):
    ok: bool
    moveUci: str | None
    timeMs: int
    error: str | None
    errorType: str | None
    output: str | None


@router.get("", response_model=list[BotOut])
async def list_bots(user: CurrentUser, session: DbSession) -> list[BotOut]:
    bots = await svc.list_bots(session, user)
    return [
        BotOut(
            id=str(b.id),
            versionNo=b.version_no,
            entry=b.entry,
            isActive=b.is_active,
            createdAt=b.created_at.isoformat(),
        )
        for b in bots
    ]


@router.post("", status_code=201, response_model=BotOut)
async def create_bot(
    body: BotCreateIn, user: CurrentUser, session: DbSession
) -> BotOut:
    bot = await svc.create_bot(session, user, body.code, body.entry)
    return BotOut(
        id=str(bot.id),
        versionNo=bot.version_no,
        entry=bot.entry,
        isActive=bot.is_active,
        createdAt=bot.created_at.isoformat(),
    )


@router.get("/{bot_id}", response_model=BotOut)
async def get_bot(bot_id: int, user: CurrentUser, session: DbSession) -> BotOut:
    bot = await svc.get_bot(session, user, bot_id)
    return BotOut(
        id=str(bot.id),
        versionNo=bot.version_no,
        entry=bot.entry,
        isActive=bot.is_active,
        createdAt=bot.created_at.isoformat(),
    )


@router.post("/{bot_id}/test", response_model=BotTestOut)
async def test_bot(
    bot_id: int, body: BotTestIn, user: CurrentUser, session: DbSession
) -> BotTestOut:
    result = await svc.test_move(session, user, bot_id, body.fen.strip())
    return BotTestOut(
        ok=result["ok"],
        moveUci=result["moveUci"],
        timeMs=result["timeMs"],
        error=result["error"],
        errorType=result["errorType"],
        output=result["output"] or None,
    )
