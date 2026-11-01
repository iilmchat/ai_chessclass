"""Роутер /api/v1/chess (Design §12.2): инсайт позиции, партии, блюндеры."""

import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
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


class GameUploadIn(CamelModel):
    pgn: str = Field(min_length=10)


class GameUploadOut(CamelModel):
    gameId: str
    status: str


class GameStatusOut(CamelModel):
    gameId: str
    status: str
    blunderCount: int
    summary: dict


class BlunderOut(CamelModel):
    ply: int
    fenBefore: str
    playedSan: str
    playedUci: str
    bestSan: str
    bestUci: str
    deltaCp: int
    classification: str
    explanation: str | None = None


class BlundersOut(CamelModel):
    gameId: str
    status: str
    blunders: list[BlunderOut]
    summary: dict


class BlunderExplainIn(CamelModel):
    ply: int


class BlunderExplainOut(CamelModel):
    ply: int
    explanation: str
    modelUsed: str


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


# --- партии и блюндеры (S-12)


@router.post("/games/upload", status_code=202, response_model=GameUploadOut)
async def upload_game(
    body: GameUploadIn, user: CurrentUser, session: DbSession
) -> GameUploadOut:
    result = await svc.upload_game(session, user, body.pgn)
    return GameUploadOut(gameId=str(result["game_id"]), status=result["status"])


@router.get("/games/{game_id}", response_model=GameStatusOut)
async def game_status(game_id: int, user: CurrentUser, session: DbSession) -> GameStatusOut:
    analysis = await svc.get_analysis_for_user(session, user, game_id)
    sf = analysis.sf
    return GameStatusOut(
        gameId=str(game_id),
        status=analysis.status.value,
        blunderCount=len(sf.get("blunders") or []),
        summary=sf.get("summary") or {},
    )


@router.get("/games/{game_id}/blunders", response_model=BlundersOut)
async def game_blunders(
    game_id: int, user: CurrentUser, session: DbSession
) -> BlundersOut:
    data = await svc.get_blunders(session, user, game_id)
    return BlundersOut(
        gameId=str(data["game_id"]),
        status=data["status"],
        blunders=[BlunderOut(**b) for b in data["blunders"]],
        summary=data["summary"],
    )


@router.post(
    "/games/{game_id}/blunders/explain", response_model=BlunderExplainOut
)
async def explain_blunder(
    game_id: int,
    body: BlunderExplainIn,
    user: CurrentUser,
    session: DbSession,
    request: Request,
) -> BlunderExplainOut:
    data = await svc.explain_blunder(
        session, request.app.state.redis, user, game_id, body.ply
    )
    return BlunderExplainOut(
        ply=data["ply"],
        explanation=data["explanation"],
        modelUsed=data["model_used"],
    )


@router.get("/games/{game_id}/events", summary="SSE прогресс разбора (S-12)")
async def game_events(
    game_id: int, user: CurrentUser, session: DbSession, request: Request
) -> StreamingResponse:
    await svc.get_analysis_for_user(session, user, game_id)
    channel = svc.progress_channel(game_id)

    async def stream():
        pubsub = request.app.state.redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            analysis = await svc.get_analysis_for_user(session, user, game_id)
            yield f"event: status\ndata: {json.dumps({'status': analysis.status.value})}\n\n"
            if analysis.status.value in ("done", "failed"):
                # Поздний подписчик: результат уже в БД, pubsub-события не будет.
                return
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=5.0
                )
                if message and message.get("data"):
                    payload = message["data"]
                    if isinstance(payload, bytes):
                        payload = payload.decode("utf-8")
                    yield f"event: progress\ndata: {payload}\n\n"
                    try:
                        if json.loads(payload).get("status") in ("done", "failed"):
                            break
                    except (ValueError, TypeError):
                        continue
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream")
