"""S-51: PvP-комнаты, быстрый матч, отдельный Elo и жалобы."""

import logging
import secrets
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.authz import (
    ensure_can_access_pvp_room,
    teacher_student_ids,
)
from core.errors import AppError
from domains.auth.models import User, UserRole
from domains.bot_lab.models import BotVersion
from domains.profile.models import UserProfile
from domains.pvp.models import PvpComplaint, PvpRating, PvpRoom
from domains.tournaments import service as tournaments_svc
from domains.tournaments.models import Tournament, TournamentMatch

logger = logging.getLogger(__name__)
K_FACTOR = 24.0


async def _active_bot(
    session: AsyncSession, user_id: int, bot_id: int
) -> BotVersion:
    bot = await session.get(BotVersion, bot_id)
    if bot is None or bot.user_id != user_id or not bot.is_active:
        raise AppError("pvp_bot_not_found", "Активный бот не найден", 404)
    return bot


async def _rating(session: AsyncSession, user_id: int) -> PvpRating:
    row = await session.get(PvpRating, user_id)
    if row is None:
        row = PvpRating(user_id=user_id, elo=Decimal("1000"))
        session.add(row)
        await session.flush()
    return row


async def _new_code(session: AsyncSession) -> str:
    for _ in range(5):
        code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8].upper()
        exists = await session.scalar(
            select(PvpRoom.id).where(PvpRoom.code == code)
        )
        if exists is None:
            return code
    raise AppError("pvp_code_failed", "Не удалось создать код комнаты", 503)


async def create_room(
    session: AsyncSession,
    user: User,
    *,
    bot_id: int,
    rated: bool = True,
) -> PvpRoom:
    await _active_bot(session, user.id, bot_id)
    active = await session.scalar(
        select(PvpRoom.id).where(
            PvpRoom.status.in_(("waiting", "ready", "running")),
            (PvpRoom.host_user_id == user.id)
            | (PvpRoom.guest_user_id == user.id),
        )
    )
    if active is not None:
        raise AppError("pvp_room_active", "У вас уже есть активная комната", 409)
    room = PvpRoom(
        code=await _new_code(session),
        host_user_id=user.id,
        host_bot_id=bot_id,
        status="waiting",
        rated=rated,
    )
    session.add(room)
    await session.flush()
    return room


async def join_room(
    session: AsyncSession, user: User, *, code: str, bot_id: int
) -> PvpRoom:
    await _active_bot(session, user.id, bot_id)
    room = (
        await session.execute(
            select(PvpRoom).where(PvpRoom.code == code.strip().upper()).with_for_update()
        )
    ).scalar_one_or_none()
    if room is None:
        raise AppError("pvp_room_not_found", "Комната не найдена", 404)
    if room.status != "waiting":
        raise AppError("pvp_room_not_waiting", "Комната уже занята", 409)
    if room.host_user_id == user.id:
        raise AppError("pvp_room_own", "Нельзя войти в свою комнату", 422)
    room.guest_user_id = user.id
    room.guest_bot_id = bot_id
    room.status = "ready"
    await session.flush()
    return room


async def quick_match(
    session: AsyncSession, user: User, *, bot_id: int
) -> tuple[PvpRoom, bool]:
    """Найти waiting-комнату рядом по PvP Elo или создать новую."""
    await _active_bot(session, user.id, bot_id)
    me = await _rating(session, user.id)
    candidates = list(
        (
            await session.execute(
                select(PvpRoom)
                .where(
                    PvpRoom.status == "waiting",
                    PvpRoom.host_user_id != user.id,
                )
                .order_by(PvpRoom.id.desc())
                .limit(30)
            )
        ).scalars()
    )
    for room in candidates:
        host_rating = await _rating(session, room.host_user_id)
        if abs(float(host_rating.elo) - float(me.elo)) <= 300:
            return await join_room(session, user, code=room.code, bot_id=bot_id), True
    return await create_room(session, user, bot_id=bot_id), False


async def start_room(
    session: AsyncSession, user: User, room_id: int
) -> tuple[PvpRoom, Tournament]:
    room = (
        await session.execute(
            select(PvpRoom).where(PvpRoom.id == room_id).with_for_update()
        )
    ).scalar_one_or_none()
    if room is None:
        raise AppError("pvp_room_not_found", "Комната не найдена", 404)
    if room.host_user_id != user.id:
        raise AppError("pvp_room_forbidden", "Запускать комнату может хозяин", 403)
    if room.status != "ready" or room.guest_bot_id is None:
        raise AppError("pvp_room_not_ready", "Нужен второй участник", 409)
    tournament = await tournaments_svc.create_tournament(
        session,
        user,
        name=f"PvP {room.code}",
        format="bracket",
        bot_ids=[room.host_bot_id, room.guest_bot_id],
    )
    tournament.meta = {**(tournament.meta or {}), "pvpRoomId": room.id}
    room.tournament_id = tournament.id
    room.status = "running"
    room.started_at = datetime.now(UTC)
    await session.flush()
    return room, tournament


async def _apply_elo(
    session: AsyncSession, room: PvpRoom, result: str
) -> None:
    if room.guest_user_id is None:
        return
    host = await _rating(session, room.host_user_id)
    guest = await _rating(session, room.guest_user_id)
    if room.rated:
        expected = 1.0 / (
            1.0 + 10 ** ((float(guest.elo) - float(host.elo)) / 400.0)
        )
        score = 1.0 if result == "a" else 0.0 if result == "b" else 0.5
        delta = round(K_FACTOR * (score - expected), 1)
        host.elo = Decimal(str(max(100.0, float(host.elo) + delta)))
        guest.elo = Decimal(str(max(100.0, float(guest.elo) - delta)))
    if result == "a":
        host.wins += 1
        guest.losses += 1
    elif result == "b":
        guest.wins += 1
        host.losses += 1
    else:
        host.draws += 1
        guest.draws += 1


async def finalize_tournament(
    session: AsyncSession, tournament_id: int
) -> PvpRoom | None:
    """Вызывается tournament-job после завершения/отмены PvP-турнира."""
    room = (
        await session.execute(
            select(PvpRoom)
            .where(PvpRoom.tournament_id == tournament_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if room is None or room.status == "done":
        return room
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        return room
    if tournament.status == "cancelled":
        room.status = "cancelled"
        room.finished_at = datetime.now(UTC)
        await session.flush()
        return room
    if tournament.status == "failed":
        room.status = "failed"
        room.finished_at = datetime.now(UTC)
        await session.flush()
        return room
    match = (
        await session.execute(
            select(TournamentMatch)
            .where(TournamentMatch.tournament_id == tournament_id)
            .order_by(TournamentMatch.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if match is not None:
        await _apply_elo(session, room, match.result)
    room.status = "done"
    room.finished_at = datetime.now(UTC)
    await session.flush()
    return room


async def get_room(session: AsyncSession, room_id: int) -> PvpRoom:
    room = await session.get(PvpRoom, room_id)
    if room is None:
        raise AppError("pvp_room_not_found", "Комната не найдена", 404)
    return room


async def my_room(session: AsyncSession, user: User) -> PvpRoom:
    """Активная комната пользователя (waiting/ready/running) — для UI S-65."""
    room = await session.scalar(
        select(PvpRoom).where(
            PvpRoom.status.in_(("waiting", "ready", "running")),
            (PvpRoom.host_user_id == user.id) | (PvpRoom.guest_user_id == user.id),
        )
    )
    if room is None:
        raise AppError("pvp_room_not_found", "Активной комнаты нет", 404)
    return room


async def cancel_room(
    session: AsyncSession, user: User, room_id: int, redis=None
) -> PvpRoom:
    room = await get_room(session, room_id)
    if room.host_user_id != user.id:
        raise AppError("pvp_room_forbidden", "Отменять может хозяин", 403)
    if room.status in ("done", "cancelled"):
        return room
    if room.tournament_id is not None:
        await tournaments_svc.cancel_tournament(
            session, room.tournament_id, redis
        )
    room.status = "cancelled"
    room.finished_at = datetime.now(UTC)
    await session.flush()
    return room


async def add_complaint(
    session: AsyncSession, user: User, room_id: int, reason: str
) -> PvpComplaint:
    room = await get_room(session, room_id)
    if user.id not in (room.host_user_id, room.guest_user_id):
        raise AppError("pvp_room_forbidden", "Жалоба только от участника", 403)
    text = reason.strip()
    if len(text) < 5:
        raise AppError("pvp_complaint_short", "Опишите причину", 422)
    complaint = PvpComplaint(room_id=room_id, reporter_id=user.id, reason=text[:2000])
    session.add(complaint)
    await session.flush()

    # S-68: teacher-событие «жалоба» учителям классов обоих игроков.
    try:
        from domains.telegram import service as telegram_svc

        involved = [room.host_user_id, room.guest_user_id, user.id]
        for child_user_id in {
            int(value) for value in involved if value is not None
        }:
            await telegram_svc.enqueue_teacher_events(
                session,
                child_user_id=child_user_id,
                kind="teacher_complaint",
                text=f"Новая жалоба в PvP-матче №{room_id}",
            )
    except Exception as exc:  # noqa: BLE001 — жалоба важнее уведомлений
        logger.warning("pvp: teacher event не поставлен: %s", exc)
    return complaint


async def list_complaints(
    session: AsyncSession, user: User
) -> list[PvpComplaint]:
    stmt = select(PvpComplaint).order_by(PvpComplaint.id.desc())
    # S-91: teacher — только жалобы комнат со своими учениками.
    if user.role is UserRole.TEACHER:
        student_ids = teacher_student_ids(user.id)
        stmt = stmt.join(PvpRoom, PvpRoom.id == PvpComplaint.room_id).where(
            (PvpRoom.host_user_id.in_(student_ids))
            | (PvpRoom.guest_user_id.in_(student_ids))
        )
    return list((await session.execute(stmt)).scalars())


async def get_complaint(session: AsyncSession, complaint_id: int) -> PvpComplaint:
    complaint = await session.get(PvpComplaint, complaint_id)
    if complaint is None:
        raise AppError("pvp_complaint_not_found", "Жалоба не найдена", 404)
    return complaint


async def review_complaint(
    session: AsyncSession,
    reviewer: User,
    complaint_id: int,
    *,
    status: str,
    note: str | None,
) -> PvpComplaint:
    """open → reviewed|rejected (S-65): вердикт за учителем (ADR-005)."""
    complaint = await get_complaint(session, complaint_id)
    room = await get_room(session, complaint.room_id)
    await ensure_can_access_pvp_room(reviewer, room, session)
    if complaint.status != "open":
        raise AppError("pvp_complaint_reviewed", "Жалоба уже разобрана", 409)
    if status not in ("reviewed", "rejected"):
        raise AppError("pvp_complaint_status", "Неизвестный статус", 422)
    complaint.status = status
    complaint.reviewed_by = reviewer.id
    from datetime import UTC, datetime

    complaint.reviewed_at = datetime.now(UTC)
    complaint.note = (note or None) and note[:2000]
    await session.flush()
    return complaint


async def leaderboard(session: AsyncSession, limit: int = 50) -> list[dict]:
    rows = (
        await session.execute(
            select(PvpRating, User, UserProfile)
            .join(User, User.id == PvpRating.user_id)
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .order_by(PvpRating.elo.desc(), PvpRating.wins.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "user_id": user.id,
            "email": user.email,
            "display_name": profile.display_name if profile else None,
            "elo": float(rating.elo),
            "wins": rating.wins,
            "losses": rating.losses,
            "draws": rating.draws,
        }
        for rating, user, profile in rows
    ]


async def get_replay(
    session: AsyncSession, room_id: int, match_id: int
):
    room = await get_room(session, room_id)
    if room.tournament_id is None:
        raise AppError("pvp_not_started", "Матч ещё не начался", 409)
    return await tournaments_svc.get_replay(
        session, room.tournament_id, match_id
    )
