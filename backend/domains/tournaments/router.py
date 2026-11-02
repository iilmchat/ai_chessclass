"""Роутер турниров (S-45): создание/просмотр/экспорт без LLM."""

import csv
import io
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.base import CamelModel
from domains.auth.deps import CurrentUser, DbSession, require_role
from domains.auth.models import User, UserRole
from domains.profile.models import UserProfile
from domains.tournaments import service as svc
from domains.tournaments.models import (
    Tournament,
    TournamentMatch,
    TournamentParticipant,
)

router = APIRouter(prefix="/tournaments", tags=["tournaments"])
admin_router = APIRouter(prefix="/admin/tournaments", tags=["tournaments"])

TeacherOrAdmin = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]
ReadRoles = Annotated[
    User,
    Depends(require_role(UserRole.TEACHER, UserRole.ADMIN, UserRole.AUDITOR)),
]


class TournamentCreateIn(CamelModel):
    name: str = Field(min_length=2, max_length=120)
    format: str = Field(default="bracket", pattern=r"^(bracket|round_robin)$")
    bot_version_ids: list[int] = Field(min_length=2, max_length=16)


class TournamentOut(CamelModel):
    id: str
    name: str
    format: str
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    meta: dict


class ParticipantOut(CamelModel):
    bot_version_id: str
    user_id: str
    email: str | None
    display_name: str | None
    seed: int
    wins: int
    losses: int
    draws: int
    points: int
    rank: int | None


class MatchOut(CamelModel):
    round_no: int
    match_no: int
    bot_a_id: str
    bot_b_id: str
    winner_id: str | None
    result: str
    moves_count: int
    duration_ms: int


class TournamentDetailOut(TournamentOut):
    participants: list[ParticipantOut]
    matches: list[MatchOut]


def _out(t: Tournament) -> TournamentOut:
    return TournamentOut(
        id=str(t.id),
        name=t.name,
        format=t.format,
        status=t.status,
        created_at=t.created_at,
        started_at=t.started_at,
        finished_at=t.finished_at,
        meta=t.meta or {},
    )


async def _detail(
    session: AsyncSession,
    tournament: Tournament,
    participants: list[TournamentParticipant],
    matches: list[TournamentMatch],
) -> TournamentDetailOut:
    user_ids = {p.user_id for p in participants}
    users = {
        u.id: u
        for u in (
            await session.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars()
    }
    profiles = {
        p.user_id: p
        for p in (
            await session.execute(
                select(UserProfile).where(UserProfile.user_id.in_(user_ids))
            )
        ).scalars()
    }
    base = _out(tournament)
    return TournamentDetailOut(
        **base.model_dump(),
        participants=[
            ParticipantOut(
                bot_version_id=str(p.bot_version_id),
                user_id=str(p.user_id),
                email=users[p.user_id].email if p.user_id in users else None,
                display_name=(
                    profiles[p.user_id].display_name
                    if p.user_id in profiles
                    else None
                ),
                seed=p.seed,
                wins=p.wins,
                losses=p.losses,
                draws=p.draws,
                points=p.points,
                rank=p.rank,
            )
            for p in participants
        ],
        matches=[
            MatchOut(
                round_no=m.round_no,
                match_no=m.match_no,
                bot_a_id=str(m.bot_a_id),
                bot_b_id=str(m.bot_b_id),
                winner_id=str(m.winner_id) if m.winner_id is not None else None,
                result=m.result,
                moves_count=m.moves_count,
                duration_ms=m.duration_ms,
            )
            for m in matches
        ],
    )


@router.get("", response_model=list[TournamentOut])
async def list_tournaments(
    _user: CurrentUser, session: DbSession
) -> list[TournamentOut]:
    return [_out(t) for t in await svc.list_tournaments(session)]


@router.get("/{tournament_id}", response_model=TournamentDetailOut)
async def get_tournament(
    tournament_id: int, _user: CurrentUser, session: DbSession
) -> TournamentDetailOut:
    tournament, participants, matches = await svc.get_tournament(
        session, tournament_id
    )
    return await _detail(session, tournament, participants, matches)


@admin_router.post("", status_code=201, response_model=TournamentDetailOut)
async def create_tournament(
    body: TournamentCreateIn,
    teacher: TeacherOrAdmin,
    session: DbSession,
) -> TournamentDetailOut:
    tournament = await svc.run_tournament(
        session,
        teacher,
        name=body.name,
        format=body.format,
        bot_ids=body.bot_version_ids,
    )
    await session.commit()
    tournament, participants, matches = await svc.get_tournament(
        session, tournament.id
    )
    return await _detail(session, tournament, participants, matches)


@admin_router.get("/{tournament_id}/export.csv")
async def export_tournament(
    tournament_id: int, _guard: ReadRoles, session: DbSession
) -> Response:
    tournament, participants, matches = await svc.get_tournament(
        session, tournament_id
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["rank", "bot_version_id", "user_id", "seed", "wins", "losses", "draws", "points"]
    )
    for p in participants:
        writer.writerow(
            [p.rank or "", p.bot_version_id, p.user_id, p.seed, p.wins, p.losses, p.draws, p.points]
        )
    writer.writerow([])
    writer.writerow(["round", "match", "bot_a", "bot_b", "winner", "result", "moves"])
    for m in matches:
        writer.writerow(
            [
                m.round_no,
                m.match_no,
                m.bot_a_id,
                m.bot_b_id,
                m.winner_id or "",
                m.result,
                m.moves_count,
            ]
        )
    filename = f"tournament-{tournament.id}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
