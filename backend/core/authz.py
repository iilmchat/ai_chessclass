"""S-91: object-level authorization (BOLA fix).

Единые проверки владения объектом. Правила:
- admin — доступ ко всему;
- student — только свои объекты;
- teacher — объекты учеников своих классов (classes/class_members);
- auditor — только read-only scope (flags/audit/reports), без доступа к
  профилям/ботам/партиям/сдачам.

404 — объект не существует; 403 — существует, но нет прав. Это осознанно
разделяет «не найдено» и «чужое»: BOLA-тесты ожидают 403 на чужой объект.
"""

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.errors import AppError
from domains.auth.models import User, UserRole
from domains.classes.models import ClassMember, Classroom


def _forbidden(detail: str) -> AppError:
    return AppError("auth_forbidden", detail, 403)


def teacher_student_ids(teacher_id: int) -> Select[int]:
    """Подзапрос: user_id учеников классов учителя (для фильтров списков)."""
    return (
        select(ClassMember.user_id)
        .join(Classroom, Classroom.id == ClassMember.class_id)
        .where(Classroom.teacher_id == teacher_id)
    )


async def teacher_owns_student(
    session: AsyncSession, teacher_id: int, student_id: int
) -> bool:
    return (
        await session.scalar(
            teacher_student_ids(teacher_id)
            .where(ClassMember.user_id == student_id)
            .limit(1)
        )
        is not None
    )


async def auditor_has_scope(
    session: AsyncSession, user: User, scope: str
) -> bool:
    if user.role is not UserRole.AUDITOR:
        return False
    from domains.profile.models import UserProfile

    profile = await session.get(UserProfile, user.id)
    scopes = (profile.prefs or {}).get("auditor_scope", {}) if profile else {}
    return scopes.get(scope) is True


async def ensure_auditor_scope(
    session: AsyncSession, user: User, scope: str
) -> None:
    if not await auditor_has_scope(session, user, scope):
        raise _forbidden(f"Нет scope auditor: {scope}")


async def ensure_can_access_student_data(
    user: User,
    student_id: int,
    session: AsyncSession,
    *,
    auditor_scope: str | None = None,
) -> None:
    """Профиль/прогресс/навыки/карточка ученика."""
    if user.role is UserRole.ADMIN or user.id == student_id:
        return
    if user.role is UserRole.TEACHER and await teacher_owns_student(
        session, user.id, student_id
    ):
        return
    if user.role is UserRole.AUDITOR and auditor_scope:
        if await auditor_has_scope(session, user, auditor_scope):
            return
    raise _forbidden("Нет доступа к данным ученика")


async def ensure_can_access_report(
    user: User, report_id: int, session: AsyncSession
):
    """PDF: владелец-ученик, запросивший/свой ученик, admin, auditor scope."""
    from domains.reports.models import ReportPdf

    record = await session.get(ReportPdf, report_id)
    if record is None:
        raise AppError("report_not_found", "Отчёт не найден", 404)
    if user.role is UserRole.ADMIN or user.id == record.student_id:
        return record
    if user.role is UserRole.TEACHER and (
        record.requested_by == user.id
        or await teacher_owns_student(session, user.id, record.student_id)
    ):
        return record
    if user.role is UserRole.AUDITOR and await auditor_has_scope(
        session, user, "reports"
    ):
        return record
    raise _forbidden("Нет доступа к отчёту")


async def ensure_can_access_bot(user: User, bot_id: int, session: AsyncSession):
    """Бот: владелец, admin, учитель ученика-владельца."""
    from domains.bot_lab.models import BotVersion

    bot = await session.get(BotVersion, bot_id)
    if bot is None:
        raise AppError("bot_not_found", "Бот не найден", 404)
    if user.role is UserRole.ADMIN or bot.user_id == user.id:
        return bot
    if user.role is UserRole.TEACHER and await teacher_owns_student(
        session, user.id, bot.user_id
    ):
        return bot
    raise _forbidden("Нет доступа к боту")


async def ensure_can_access_game(user: User, game_id: int, session: AsyncSession):
    """Партия/анализ: владелец, admin, учитель ученика-владельца."""
    from domains.chess_lab.models import ChessGame

    game = await session.get(ChessGame, game_id)
    if game is None:
        raise AppError("game_not_found", "Партия не найдена", 404)
    if user.role is UserRole.ADMIN or game.user_id == user.id:
        return game
    if user.role is UserRole.TEACHER and await teacher_owns_student(
        session, user.id, game.user_id
    ):
        return game
    raise _forbidden("Нет доступа к партии")


async def ensure_can_access_submission(
    user: User, submission_id: int, session: AsyncSession
):
    """Сдача: владелец, admin, учитель ученика-владельца."""
    from domains.python_teacher.models import PySubmission

    submission = await session.get(PySubmission, submission_id)
    if submission is None:
        raise AppError("submission_not_found", "Сдача не найдена", 404)
    if user.role is UserRole.ADMIN or submission.user_id == user.id:
        return submission
    if user.role is UserRole.TEACHER and await teacher_owns_student(
        session, user.id, submission.user_id
    ):
        return submission
    raise _forbidden("Можно смотреть только сдачи своих учеников")


async def ensure_can_access_pvp_room(
    user: User, room, session: AsyncSession
) -> None:
    """PvP-комната: участник, admin, учитель участника из своего класса."""
    if user.role is UserRole.ADMIN:
        return
    if user.id in (room.host_user_id, room.guest_user_id):
        return
    if user.role is UserRole.TEACHER:
        for player_id in (room.host_user_id, room.guest_user_id):
            if player_id is not None and await teacher_owns_student(
                session, user.id, player_id
            ):
                return
    raise _forbidden("Нет доступа к комнате")
