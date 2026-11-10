"""S-51: PvP-комнаты, quick-match, SSE/replay, лидерборд и жалобы."""

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import Field

from core.authz import ensure_can_access_pvp_room
from core.base import CamelModel
from core.errors import AppError
from core.ratelimit import enforce_rate_limit
from domains.audit import service as audit_svc
from domains.auth.deps import CurrentUser, DbSession, require_role
from domains.auth.models import User, UserRole
from domains.pvp import service as svc
from domains.pvp.models import PvpComplaint, PvpRoom

router = APIRouter(prefix="/pvp", tags=["pvp"])
admin_router = APIRouter(prefix="/admin/pvp", tags=["pvp"])
AdminOrTeacher = Annotated[
    User, Depends(require_role(UserRole.ADMIN, UserRole.TEACHER))
]


class RoomCreateIn(CamelModel):
    bot_version_id: int
    rated: bool = True


class RoomJoinIn(CamelModel):
    code: str = Field(min_length=4, max_length=16)
    bot_version_id: int


class QuickMatchIn(CamelModel):
    bot_version_id: int


class ComplaintIn(CamelModel):
    reason: str = Field(min_length=5, max_length=2000)


class RoomOut(CamelModel):
    id: str
    code: str
    host_user_id: str
    host_bot_id: str
    guest_user_id: str | None
    guest_bot_id: str | None
    status: str
    rated: bool
    tournament_id: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class QuickMatchOut(CamelModel):
    room: RoomOut
    matched: bool


class LeaderboardOut(CamelModel):
    user_id: str
    email: str
    display_name: str | None
    elo: float
    wins: int
    losses: int
    draws: int


class ComplaintOut(CamelModel):
    id: str
    room_id: str
    reporter_id: str
    reason: str
    status: str
    created_at: datetime
    note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class ComplaintReviewIn(CamelModel):
    status: str = Field(pattern=r"^(reviewed|rejected)$")
    note: str | None = Field(default=None, max_length=2000)


class PvpMatchOut(CamelModel):
    id: str
    round_no: int
    match_no: int
    bot_a_id: str
    bot_b_id: str
    winner_id: str | None
    result: str
    moves_count: int
    duration_ms: int


class PvpMoveOut(CamelModel):
    ply: int
    fen: str
    uci: str
    agent: str
    think_ms: int
    sf_sample: bool


class PvpReplayOut(CamelModel):
    match: PvpMatchOut
    moves: list[PvpMoveOut]


def _out(room: PvpRoom) -> RoomOut:
    return RoomOut(
        id=str(room.id),
        code=room.code,
        host_user_id=str(room.host_user_id),
        host_bot_id=str(room.host_bot_id),
        guest_user_id=(
            str(room.guest_user_id) if room.guest_user_id is not None else None
        ),
        guest_bot_id=(
            str(room.guest_bot_id) if room.guest_bot_id is not None else None
        ),
        status=room.status,
        rated=room.rated,
        tournament_id=(
            str(room.tournament_id) if room.tournament_id is not None else None
        ),
        created_at=room.created_at,
        started_at=room.started_at,
        finished_at=room.finished_at,
    )


def _complaint_out(row: PvpComplaint) -> ComplaintOut:
    return ComplaintOut(
        id=str(row.id),
        room_id=str(row.room_id),
        reporter_id=str(row.reporter_id),
        reason=row.reason,
        status=row.status,
        created_at=row.created_at,
        note=row.note,
        reviewed_by=str(row.reviewed_by) if row.reviewed_by else None,
        reviewed_at=row.reviewed_at,
    )


async def _enqueue_tournament(
    tournament_id: int, user_id: int, role: str, trace_id: str | None = None
) -> None:
    from arq.connections import RedisSettings, create_pool

    from core.config import settings

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job(
            "run_tournament_job",
            tournament_id,
            user_id,
            role,
            trace_id,
            _job_id=f"tournament:{tournament_id}",
        )
    finally:
        await pool.aclose()


@router.post("/rooms", status_code=201, response_model=RoomOut)
async def create_room(
    body: RoomCreateIn,
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> RoomOut:
    await enforce_rate_limit(
        request.app.state.redis,
        f"pvp-room:{user.id}",
        limit=10,
        window_s=60,
    )
    room = await svc.create_room(
        session, user, bot_id=body.bot_version_id, rated=body.rated
    )
    await audit_svc.record(
        session,
        user,
        "pvp.room.create",
        target_type="pvp_room",
        target_id=room.id,
        request=request,
        meta={"rated": room.rated},
    )
    await session.commit()
    return _out(room)


@router.post("/rooms/join", response_model=RoomOut)
async def join_room(
    body: RoomJoinIn,
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> RoomOut:
    room = await svc.join_room(
        session, user, code=body.code, bot_id=body.bot_version_id
    )
    await audit_svc.record(
        session,
        user,
        "pvp.room.join",
        target_type="pvp_room",
        target_id=room.id,
        request=request,
    )
    await session.commit()
    return _out(room)


@router.post("/quick-match", response_model=QuickMatchOut)
async def quick_match(
    body: QuickMatchIn,
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> QuickMatchOut:
    await enforce_rate_limit(
        request.app.state.redis,
        f"pvp-quick:{user.id}",
        limit=10,
        window_s=60,
    )
    room, matched = await svc.quick_match(
        session, user, bot_id=body.bot_version_id
    )
    await audit_svc.record(
        session,
        user,
        "pvp.room.quick",
        target_type="pvp_room",
        target_id=room.id,
        request=request,
        meta={"matched": matched},
    )
    await session.commit()
    return QuickMatchOut(room=_out(room), matched=matched)


@router.get("/rooms/mine", response_model=RoomOut)
async def my_room(user: CurrentUser, session: DbSession) -> RoomOut:
    """S-65: активная комната пользователя — возврат на страницу после F5."""
    return _out(await svc.my_room(session, user))


@router.get("/rooms/{room_id}", response_model=RoomOut)
async def get_room(
    room_id: int, user: CurrentUser, session: DbSession
) -> RoomOut:
    room = await svc.get_room(session, room_id)
    await ensure_can_access_pvp_room(user, room, session)
    return _out(room)


@router.post("/rooms/{room_id}/start", response_model=RoomOut)
async def start_room(
    room_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> RoomOut:
    room, tournament = await svc.start_room(session, user, room_id)
    await audit_svc.record(
        session,
        user,
        "pvp.room.start",
        target_type="pvp_room",
        target_id=room.id,
        request=request,
        meta={"tournamentId": tournament.id},
    )
    await session.commit()
    from core.tracing import current_trace_id_optional

    await _enqueue_tournament(
        tournament.id, user.id, user.role.value, current_trace_id_optional()
    )
    return _out(room)


@router.post("/rooms/{room_id}/cancel", response_model=RoomOut)
async def cancel_room(
    room_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> RoomOut:
    room = await svc.cancel_room(
        session, user, room_id, request.app.state.redis
    )
    await audit_svc.record(
        session,
        user,
        "pvp.room.cancel",
        target_type="pvp_room",
        target_id=room.id,
        request=request,
    )
    await session.commit()
    return _out(room)


@router.get("/rooms/{room_id}/events")
async def room_events(
    room_id: int,
    user: CurrentUser,
    session: DbSession,
    request: Request,
) -> StreamingResponse:
    room = await svc.get_room(session, room_id)
    await ensure_can_access_pvp_room(user, room, session)
    if room.tournament_id is None:
        raise AppError("pvp_not_started", "Матч ещё не начался", 409)
    channel = f"tournaments:{room.tournament_id}"

    async def stream():
        pubsub = request.app.state.redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            initial = json.dumps(
                {"status": room.status, "tournamentId": room.tournament_id}
            )
            yield f"event: status\ndata: {initial}\n\n"
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
                        if json.loads(payload).get("status") in (
                            "done",
                            "cancelled",
                            "failed",
                        ):
                            break
                    except (ValueError, TypeError):
                        continue
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/rooms/{room_id}/replay", response_model=PvpReplayOut)
async def room_replay(
    room_id: int,
    match_id: int,
    user: CurrentUser,
    session: DbSession,
) -> PvpReplayOut:
    room = await svc.get_room(session, room_id)
    await ensure_can_access_pvp_room(user, room, session)
    match, moves = await svc.get_replay(session, room_id, match_id)
    return PvpReplayOut(
        match=PvpMatchOut(
            id=str(match.id),
            round_no=match.round_no,
            match_no=match.match_no,
            bot_a_id=str(match.bot_a_id),
            bot_b_id=str(match.bot_b_id),
            winner_id=(
                str(match.winner_id) if match.winner_id is not None else None
            ),
            result=match.result,
            moves_count=match.moves_count,
            duration_ms=match.duration_ms,
        ),
        moves=[
            PvpMoveOut(
                ply=move.ply,
                fen=move.fen,
                uci=move.uci,
                agent=move.agent,
                think_ms=move.think_ms,
                sf_sample=move.sf_sample,
            )
            for move in moves
        ],
    )


@router.get("/leaderboard", response_model=list[LeaderboardOut])
async def leaderboard(
    _user: CurrentUser, session: DbSession
) -> list[LeaderboardOut]:
    return [
        LeaderboardOut(**{**row, "user_id": str(row["user_id"])})
        for row in await svc.leaderboard(session)
    ]


@router.post("/rooms/{room_id}/complaints", response_model=ComplaintOut)
async def add_complaint(
    room_id: int,
    body: ComplaintIn,
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> ComplaintOut:
    complaint = await svc.add_complaint(session, user, room_id, body.reason)
    await audit_svc.record(
        session,
        user,
        "pvp.complaint.create",
        target_type="pvp_room",
        target_id=room_id,
        request=request,
        meta={"complaintId": complaint.id},
    )
    await session.commit()
    return _complaint_out(complaint)


@admin_router.get("/complaints", response_model=list[ComplaintOut])
async def list_complaints(
    guard: AdminOrTeacher, session: DbSession
) -> list[ComplaintOut]:
    return [
        _complaint_out(row) for row in await svc.list_complaints(session, guard)
    ]


@admin_router.patch("/complaints/{complaint_id}", response_model=ComplaintOut)
async def review_complaint(
    complaint_id: int,
    body: ComplaintReviewIn,
    guard: AdminOrTeacher,
    session: DbSession,
) -> ComplaintOut:
    """S-65: workflow жалоб — open → reviewed/rejected (note, reviewer)."""
    from domains.pvp.service import review_complaint as review

    complaint = await review(
        session, guard, complaint_id, status=body.status, note=body.note
    )
    from domains.audit import service as audit_svc

    await audit_svc.record(
        session,
        guard,
        "pvp.complaint.review",
        target_type="pvp_complaint",
        target_id=complaint.id,
        meta={"status": complaint.status},
    )
    await session.commit()
    return _complaint_out(complaint)
