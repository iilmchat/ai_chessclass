"""Бизнес-логика классов (S-40): создание, инвайты, участники, дашборд.

S-83: учитель класса подтверждает возрастную группу ученика — trusted-источник
для consent enforcement; подтверждение хранится в `user_profiles`.
"""

import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.errors import AppError
from domains.anticheat.models import AnticheatFlag, FlagStatus
from domains.auth.models import User, UserRole
from domains.bot_lab.models import BotStats
from domains.classes.models import ClassMember, Classroom
from domains.cognitive import service as cognitive_service
from domains.profile.models import AgeGroup, UserProfile

logger = logging.getLogger(__name__)

INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
INVITE_LENGTH = 8


def _normalize_code(code: str) -> str:
    return code.strip().upper()


async def _generate_invite_code(session: AsyncSession) -> str:
    for _ in range(20):
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH))
        exists = await session.scalar(
            select(Classroom.id).where(Classroom.invite_code == code)
        )
        if exists is None:
            return code
    raise AppError(
        "class_invite_generation_failed",
        "Не удалось сгенерировать код класса",
        500,
    )


async def create_class(
    session: AsyncSession, teacher: User, name: str
) -> Classroom:
    clean_name = name.strip()
    if len(clean_name) < 2:
        raise AppError("class_name_invalid", "Название класса слишком короткое", 422)
    classroom = Classroom(
        name=clean_name,
        teacher_id=teacher.id,
        invite_code=await _generate_invite_code(session),
    )
    session.add(classroom)
    await session.flush()
    logger.info("classes: teacher=%s создал класс id=%s", teacher.id, classroom.id)
    return classroom


async def list_classes(
    session: AsyncSession, user: User
) -> list[tuple[Classroom, int]]:
    counts = (
        select(ClassMember.class_id, func.count().label("member_count"))
        .group_by(ClassMember.class_id)
        .subquery()
    )
    stmt = (
        select(Classroom, func.coalesce(counts.c.member_count, 0))
        .outerjoin(counts, counts.c.class_id == Classroom.id)
        .order_by(Classroom.created_at.desc(), Classroom.id.desc())
    )
    if user.role is UserRole.STUDENT:
        stmt = stmt.join(
            ClassMember, ClassMember.class_id == Classroom.id
        ).where(ClassMember.user_id == user.id)
    elif user.role is UserRole.TEACHER:
        stmt = stmt.where(Classroom.teacher_id == user.id)
    rows = (await session.execute(stmt)).all()
    return [(classroom, int(count)) for classroom, count in rows]


async def get_class(session: AsyncSession, class_id: int) -> Classroom:
    classroom = await session.get(Classroom, class_id)
    if classroom is None:
        raise AppError("class_not_found", "Класс не найден", 404)
    return classroom


def is_manager(user: User, classroom: Classroom) -> bool:
    return user.role is UserRole.ADMIN or classroom.teacher_id == user.id


def ensure_manager(user: User, classroom: Classroom) -> None:
    if not is_manager(user, classroom):
        raise AppError("class_forbidden", "Нет доступа к этому классу", 403)


async def is_member(session: AsyncSession, class_id: int, user_id: int) -> bool:
    return (
        await session.scalar(
            select(ClassMember.user_id).where(
                ClassMember.class_id == class_id,
                ClassMember.user_id == user_id,
            )
        )
        is not None
    )


async def list_members(
    session: AsyncSession, class_id: int
) -> list[tuple[User, UserProfile | None, datetime]]:
    rows = (
        await session.execute(
            select(User, UserProfile, ClassMember.joined_at)
            .join(ClassMember, ClassMember.user_id == User.id)
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .where(ClassMember.class_id == class_id)
            .order_by(User.id)
        )
    ).all()
    return [(user, profile, joined_at) for user, profile, joined_at in rows]


async def get_class_detail(
    session: AsyncSession, user: User, class_id: int
) -> tuple[Classroom, list[tuple[User, UserProfile | None, datetime]], int]:
    classroom = await get_class(session, class_id)
    manager = is_manager(user, classroom)
    if not manager and not await is_member(session, class_id, user.id):
        raise AppError("class_forbidden", "Нет доступа к этому классу", 403)
    members = await list_members(session, class_id) if manager else []
    if manager:
        member_count = len(members)
    else:
        member_count = int(
            await session.scalar(
                select(func.count())
                .select_from(ClassMember)
                .where(ClassMember.class_id == class_id)
            )
            or 0
        )
    return classroom, members, member_count


async def add_member_by_email(
    session: AsyncSession, user: User, class_id: int, email: str
) -> tuple[User, datetime]:
    classroom = await get_class(session, class_id)
    ensure_manager(user, classroom)
    student = (
        await session.execute(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )
    ).scalar_one_or_none()
    if student is None:
        raise AppError("user_not_found", "Пользователь не найден", 404)
    if student.role is not UserRole.STUDENT:
        raise AppError(
            "class_member_role", "В класс можно добавлять только учеников", 422
        )
    existing = await session.get(ClassMember, (class_id, student.id))
    if existing is not None:
        raise AppError("class_member_exists", "Ученик уже в классе", 409)
    member = ClassMember(class_id=class_id, user_id=student.id)
    session.add(member)
    await session.flush()
    await session.refresh(member)
    logger.info("classes: class=%s + student=%s (by teacher)", class_id, student.id)
    return student, member.joined_at


async def confirm_student_age_group(
    session: AsyncSession,
    teacher: User,
    class_id: int,
    student_id: int,
    age_group: AgeGroup,
) -> tuple[UserProfile, datetime]:
    """S-83: teacher подтверждает возрастную группу ученика своего класса.

    Доступ — владелец класса или admin (`ensure_manager`); ученик обязан быть
    участником класса. Подтверждение перезаписывает self-declared age_group и
    фиксирует кто/когда подтвердил.
    """
    classroom = await get_class(session, class_id)
    ensure_manager(teacher, classroom)
    student = await session.get(User, student_id)
    if student is None:
        raise AppError("user_not_found", "Пользователь не найден", 404)
    if not await is_member(session, class_id, student_id):
        raise AppError("class_member_not_found", "Ученик не найден в классе", 404)

    profile = await session.get(UserProfile, student_id)
    if profile is None:
        profile = UserProfile(user_id=student_id)
        session.add(profile)
        await session.flush()

    confirmed_at = datetime.now(UTC)
    profile.age_group = age_group
    profile.age_group_confirmed_at = confirmed_at
    profile.age_group_confirmed_by = teacher.id
    await session.flush()
    logger.info(
        "classes: teacher=%s подтвердил age_group=%s для student=%s (class=%s)",
        teacher.id,
        age_group.value,
        student_id,
        class_id,
    )
    return profile, confirmed_at


async def join_by_code(
    session: AsyncSession, user: User, invite_code: str
) -> Classroom:
    if user.role is not UserRole.STUDENT:
        raise AppError(
            "class_student_only", "Присоединяться к классу могут только ученики", 403
        )
    classroom = (
        await session.execute(
            select(Classroom).where(
                Classroom.invite_code == _normalize_code(invite_code)
            )
        )
    ).scalar_one_or_none()
    if classroom is None:
        raise AppError("class_invite_invalid", "Код класса не найден", 404)
    existing = await session.get(ClassMember, (classroom.id, user.id))
    if existing is None:
        session.add(ClassMember(class_id=classroom.id, user_id=user.id))
        await session.flush()
        logger.info("classes: class=%s + student=%s (invite)", classroom.id, user.id)
    return classroom


async def remove_member(
    session: AsyncSession, user: User, class_id: int, member_id: int
) -> None:
    classroom = await get_class(session, class_id)
    ensure_manager(user, classroom)
    member = await session.get(ClassMember, (class_id, member_id))
    if member is None:
        raise AppError("class_member_not_found", "Ученик не найден в классе", 404)
    await session.execute(
        delete(ClassMember).where(
            ClassMember.class_id == class_id, ClassMember.user_id == member_id
        )
    )
    await session.flush()
    logger.info("classes: class=%s - student=%s", class_id, member_id)


async def rotate_invite(
    session: AsyncSession, user: User, class_id: int
) -> Classroom:
    classroom = await get_class(session, class_id)
    ensure_manager(user, classroom)
    classroom.invite_code = await _generate_invite_code(session)
    await session.flush()
    return classroom


async def dashboard(
    session: AsyncSession, user: User, class_id: int
) -> dict:
    classroom = await get_class(session, class_id)
    ensure_manager(user, classroom)
    members = await list_members(session, class_id)
    member_ids = [member.id for member, _profile, _joined in members]

    flags_by_user: dict[int, tuple[int, int]] = {}
    if member_ids:
        flag_rows = (
            await session.execute(
                select(
                    AnticheatFlag.user_id,
                    func.count(AnticheatFlag.id),
                    func.count(AnticheatFlag.id).filter(
                        AnticheatFlag.status == FlagStatus.NEW
                    ),
                )
                .where(AnticheatFlag.user_id.in_(member_ids))
                .group_by(AnticheatFlag.user_id)
            )
        ).all()
        flags_by_user = {
            int(user_id): (int(total), int(new_count))
            for user_id, total, new_count in flag_rows
        }

    stats_by_user: dict[int, BotStats] = {}
    if member_ids:
        stats_by_user = {
            int(stats.user_id): stats
            for stats in (
                await session.execute(
                    select(BotStats).where(BotStats.user_id.in_(member_ids))
                )
            ).scalars()
        }

    out_members: list[dict] = []
    for member, profile, joined_at in members:
        flags_count, new_flags = flags_by_user.get(member.id, (0, 0))
        stats = stats_by_user.get(member.id)
        out_members.append(
            {
                "userId": str(member.id),
                "email": member.email,
                "displayName": profile.display_name if profile else None,
                "level": profile.level.value if profile else "novice",
                "joinedAt": joined_at,
                "skills": await cognitive_service.scores_snapshot(session, member.id),
                "flagsCount": flags_count,
                "newFlagsCount": new_flags,
                "matchesCount": (
                    int(stats.wins + stats.losses + stats.draws) if stats else 0
                ),
                "wins": int(stats.wins) if stats else 0,
                "losses": int(stats.losses) if stats else 0,
                "draws": int(stats.draws) if stats else 0,
                "elo": float(stats.elo) if stats else 1000.0,
            }
        )

    return {
        "classId": str(classroom.id),
        "className": classroom.name,
        "memberCount": len(out_members),
        "members": out_members,
    }
