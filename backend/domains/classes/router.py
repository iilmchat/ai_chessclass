"""Роутер /api/v1/classes (S-40): классы, инвайты, участники, дашборд.

RBAC: создание/управление — teacher/admin (admin — любой класс);
ученик видит свои классы и может присоединиться по коду. Чужой учитель
получает 403 на детали/дашборд/мутации.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import EmailStr, Field

from core.base import CamelModel
from domains.auth.deps import CurrentUser, DbSession, require_role
from domains.auth.models import User, UserRole
from domains.classes import service as svc
from domains.classes.models import Classroom
from domains.profile.models import UserProfile

router = APIRouter(prefix="/classes", tags=["classes"])

TeacherOrAdmin = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]


class ClassCreateIn(CamelModel):
    name: str = Field(min_length=2, max_length=120)


class ClassJoinIn(CamelModel):
    invite_code: str = Field(min_length=4, max_length=16)


class ClassMemberAddIn(CamelModel):
    email: EmailStr


class ClassOut(CamelModel):
    id: str
    name: str
    teacher_id: str
    invite_code: str | None
    member_count: int
    created_at: datetime


class ClassMemberOut(CamelModel):
    user_id: str
    email: str
    display_name: str | None
    level: str
    joined_at: datetime


class ClassDetailOut(ClassOut):
    members: list[ClassMemberOut] = Field(default_factory=list)


class ClassSkillOut(CamelModel):
    slug: str
    title_ru: str
    domain: str
    score: float
    week: str | None


class ClassDashboardMemberOut(CamelModel):
    user_id: str
    email: str
    display_name: str | None
    level: str
    joined_at: datetime
    skills: list[ClassSkillOut]
    flags_count: int
    new_flags_count: int
    matches_count: int
    wins: int
    losses: int
    draws: int
    elo: float


class ClassDashboardOut(CamelModel):
    class_id: str
    class_name: str
    member_count: int
    members: list[ClassDashboardMemberOut]


def _class_out(
    classroom: Classroom,
    member_count: int,
    *,
    include_invite: bool,
) -> ClassOut:
    return ClassOut(
        id=str(classroom.id),
        name=classroom.name,
        teacher_id=str(classroom.teacher_id),
        invite_code=classroom.invite_code if include_invite else None,
        member_count=member_count,
        created_at=classroom.created_at,
    )


def _member_out(
    user: User, profile: UserProfile | None, joined_at: datetime
) -> ClassMemberOut:
    return ClassMemberOut(
        user_id=str(user.id),
        email=user.email,
        display_name=profile.display_name if profile else None,
        level=profile.level.value if profile else "novice",
        joined_at=joined_at,
    )


@router.get("", response_model=list[ClassOut])
async def list_classes(user: CurrentUser, session: DbSession) -> list[ClassOut]:
    rows = await svc.list_classes(session, user)
    return [
        _class_out(classroom, count, include_invite=svc.is_manager(user, classroom))
        for classroom, count in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ClassOut)
async def create_class(
    body: ClassCreateIn, teacher: TeacherOrAdmin, session: DbSession
) -> ClassOut:
    classroom = await svc.create_class(session, teacher, body.name)
    await session.commit()
    return _class_out(classroom, 0, include_invite=True)


@router.post("/join", response_model=ClassOut)
async def join_class(
    body: ClassJoinIn, user: CurrentUser, session: DbSession
) -> ClassOut:
    classroom = await svc.join_by_code(session, user, body.invite_code)
    await session.commit()
    _classroom, _members, count = await svc.get_class_detail(
        session, user, classroom.id
    )
    return _class_out(classroom, count, include_invite=False)


@router.get("/{class_id}", response_model=ClassDetailOut)
async def get_class(
    class_id: int, user: CurrentUser, session: DbSession
) -> ClassDetailOut:
    classroom, members, count = await svc.get_class_detail(session, user, class_id)
    base = _class_out(
        classroom, count, include_invite=svc.is_manager(user, classroom)
    )
    return ClassDetailOut(
        **base.model_dump(),
        members=[_member_out(member, profile, joined) for member, profile, joined in members],
    )


@router.post("/{class_id}/invite", response_model=ClassOut)
async def rotate_invite(
    class_id: int, teacher: TeacherOrAdmin, session: DbSession
) -> ClassOut:
    classroom = await svc.rotate_invite(session, teacher, class_id)
    await session.commit()
    _classroom, _members, count = await svc.get_class_detail(
        session, teacher, class_id
    )
    return _class_out(classroom, count, include_invite=True)


@router.get("/{class_id}/dashboard", response_model=ClassDashboardOut)
async def class_dashboard(
    class_id: int, teacher: TeacherOrAdmin, session: DbSession
) -> ClassDashboardOut:
    data = await svc.dashboard(session, teacher, class_id)
    return ClassDashboardOut(**data)


@router.post(
    "/{class_id}/members",
    status_code=status.HTTP_201_CREATED,
    response_model=ClassMemberOut,
)
async def add_member(
    class_id: int,
    body: ClassMemberAddIn,
    teacher: TeacherOrAdmin,
    session: DbSession,
) -> ClassMemberOut:
    student, joined_at = await svc.add_member_by_email(
        session, teacher, class_id, body.email
    )
    await session.commit()
    profile = await session.get(UserProfile, student.id)
    return _member_out(student, profile, joined_at)


@router.delete("/{class_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    class_id: int, user_id: int, teacher: TeacherOrAdmin, session: DbSession
) -> None:
    await svc.remove_member(session, teacher, class_id, user_id)
    await session.commit()
