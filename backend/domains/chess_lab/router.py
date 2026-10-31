"""Роутер /api/v1/chess (Design §12.2): инсайт позиции (S-11)."""

from fastapi import APIRouter, Query, Request
from pydantic import Field

from core.base import CamelModel
from domains.auth.deps import CurrentUser, DbSession
from domains.chess_lab import service as svc
from domains.profile.schemas import PageOut

router = APIRouter(prefix="/chess", tags=["chess_lab"])


class InsightIn(CamelModel):
    fen: str = Field(min_length=10, max_length=128)
    level: str | None = Field(
        default=None, description="Override уровня объяснения (novice|intermediate|advanced)"
    )


class EngineLineOut(CamelModel):
    multipv: int
    depth: int
    score_cp: int | None  # JSON: scoreCp
    mate: int | None
    move_uci: str  # JSON: moveUci
    pv: list[str]


class InsightOut(CamelModel):
    fen: str
    level: str
    facts: list[EngineLineOut]
    factsText: list[str]
    explanation: str
    modelUsed: str


class PositionOut(CamelModel):
    id: str
    fen: str
    meta: dict


@router.post("/insight", response_model=InsightOut)
async def insight(
    body: InsightIn, user: CurrentUser, session: DbSession, request: Request
) -> InsightOut:
    data = await svc.insight(
        session,
        request.app.state.redis,
        user,
        fen=body.fen.strip(),
        level_override=body.level,
    )
    return InsightOut(
        fen=data["fen"],
        level=data["level"],
        facts=[EngineLineOut(**item) for item in data["facts"]],
        factsText=data["factsText"],
        explanation=data["explanation"],
        modelUsed=data["modelUsed"],
    )


@router.get("/positions", response_model=PageOut)
async def list_positions(
    user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=20, ge=1, le=100, alias="limit"),
) -> PageOut:
    rows = await svc.list_positions(session, user, limit)
    return PageOut(
        items=[
            PositionOut(id=str(p.id), fen=p.fen, meta=p.meta) for p in rows
        ],
        total=len(rows),
        page=1,
        page_size=limit,
    )
