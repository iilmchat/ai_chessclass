"""S-72: RLS-изоляция классов — проверки на уровне сырого SQL.

Тесты намеренно не добавляют `WHERE user_id = ...`: видимость строк должна
обеспечивать PostgreSQL-политика, а не фильтр в коде приложения.
"""

import uuid
from decimal import Decimal
from typing import TypedDict

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import db_context, session_factory
from domains.anticheat.models import AnticheatFlag, FlagDomain, FlagKind
from domains.auth.models import UserRole
from domains.bot_lab.models import BotStats
from domains.classes.models import ClassMember, Classroom
from domains.cognitive.models import Skill, SkillDomain, SkillEvent
from tests.conftest import API, ensure_seeds, login, make_direct_user

TENANT_TABLES = ("bot_stats", "cognitive_skill_events", "anticheat_flags")


class Tenants(TypedDict):
    teacher_a: int
    teacher_b: int
    student_a: int
    student_b: int
    email_b: str
    skill_id: int


@pytest.fixture
async def tenants() -> Tenants:
    """Два учителя, два ученика и по классу; данные готовятся отдельно."""
    await ensure_seeds()
    suffix = uuid.uuid4().hex[:8]
    teacher_a = await make_direct_user(
        f"rls-teacher-a-{suffix}@e2e.chessclass", UserRole.TEACHER
    )
    teacher_b = await make_direct_user(
        f"rls-teacher-b-{suffix}@e2e.chessclass", UserRole.TEACHER
    )
    student_a = await make_direct_user(
        f"rls-student-a-{suffix}@e2e.chessclass", UserRole.STUDENT
    )
    student_b = await make_direct_user(
        f"rls-student-b-{suffix}@e2e.chessclass", UserRole.STUDENT
    )

    async with session_factory() as session:
        class_a = Classroom(
            name=f"RLS A {suffix}",
            teacher_id=teacher_a,
            invite_code=f"a-{suffix}",
        )
        class_b = Classroom(
            name=f"RLS B {suffix}",
            teacher_id=teacher_b,
            invite_code=f"b-{suffix}",
        )
        session.add_all([class_a, class_b])
        await session.flush()
        session.add_all(
            [
                ClassMember(class_id=class_a.id, user_id=student_a),
                ClassMember(class_id=class_b.id, user_id=student_b),
            ]
        )
        skill_id_raw = (await session.execute(sa.select(Skill.id))).scalars().first()
        assert skill_id_raw is not None
        skill_id = int(skill_id_raw)
        await session.commit()

    return {
        "teacher_a": teacher_a,
        "teacher_b": teacher_b,
        "student_a": student_a,
        "student_b": student_b,
        "email_b": f"rls-teacher-b-{suffix}@e2e.chessclass",
        "skill_id": skill_id,
    }


async def _add_event(student_id: int, skill_id: int) -> None:
    async with session_factory() as session:
        session.add(
            SkillEvent(
                user_id=student_id,
                skill_id=skill_id,
                domain=SkillDomain.PYTHON,
                weight=Decimal("1.000"),
                meta={"source": "rls-test"},
            )
        )
        await session.commit()


async def _add_tenant_rows(student_id: int, marker: str) -> None:
    """По одной строке в каждой RLS-таблице для ученика."""
    async with session_factory() as session:
        session.add(
            BotStats(user_id=student_id, elo=Decimal("1234.5"), wins=2)
        )
        session.add(
            AnticheatFlag(
                user_id=student_id,
                kind=FlagKind.LOW_EFFORT,
                domain=FlagDomain.PYTHON,
                confidence=Decimal("0.55"),
                evidence={"marker": marker},
            )
        )
        await session.commit()


async def _visible_user_ids(
    session: AsyncSession, table: str, user_id: int | None, role: str
) -> set[int]:
    """Сырой SELECT без фильтра, от имени принципала; фиксируем транзакцию."""
    async with db_context(user_id, role):
        rows = (
            await session.execute(sa.text(f"SELECT DISTINCT user_id FROM {table}"))
        ).all()
        await session.commit()
    return {int(row[0]) for row in rows}


async def _count_rows(
    session: AsyncSession, table: str, user_id: int | None, role: str
) -> int:
    async with db_context(user_id, role):
        count = (
            await session.execute(sa.text(f"SELECT count(*) FROM {table}"))
        ).scalar_one()
        await session.commit()
    return int(count)


async def test_teacher_b_sees_no_rows_of_student_a(tenants):
    """Тест 1: учитель B прямым SQL без WHERE не видит данные ученика A."""
    await _add_event(tenants["student_a"], tenants["skill_id"])

    async with session_factory() as session:
        count_b = await _count_rows(
            session,
            "cognitive_skill_events",
            tenants["teacher_b"],
            "teacher",
        )
        assert count_b == 0
        assert tenants["student_a"] not in await _visible_user_ids(
            session,
            "cognitive_skill_events",
            tenants["teacher_b"],
            "teacher",
        )

        visible_a = await _visible_user_ids(
            session,
            "cognitive_skill_events",
            tenants["teacher_a"],
            "teacher",
        )
        assert visible_a == {tenants["student_a"]}


async def test_admin_sees_all_tenants(tenants):
    """Тест 2: admin видит данные обоих классов без фильтров."""
    await _add_event(tenants["student_a"], tenants["skill_id"])
    await _add_event(tenants["student_b"], tenants["skill_id"])

    async with session_factory() as session:
        visible = await _visible_user_ids(
            session, "cognitive_skill_events", None, "admin"
        )
    assert {tenants["student_a"], tenants["student_b"]} <= visible


async def test_context_switch_a_b_a_has_no_leak(tenants):
    """Тест 3: A → B → A на одном соединении — каждый видит только своих."""
    await _add_event(tenants["student_a"], tenants["skill_id"])
    await _add_event(tenants["student_b"], tenants["skill_id"])

    async with session_factory() as session:
        first_a = await _visible_user_ids(
            session,
            "cognitive_skill_events",
            tenants["teacher_a"],
            "teacher",
        )
        only_b = await _visible_user_ids(
            session,
            "cognitive_skill_events",
            tenants["teacher_b"],
            "teacher",
        )
        second_a = await _visible_user_ids(
            session,
            "cognitive_skill_events",
            tenants["teacher_a"],
            "teacher",
        )

    assert first_a == {tenants["student_a"]}
    assert only_b == {tenants["student_b"]}
    assert second_a == first_a
    assert tenants["student_b"] not in first_a
    assert tenants["student_a"] not in only_b


async def test_rls_covers_all_tenant_tables(tenants):
    """Политики включены на всех трёх таблицах, а не только на событиях."""
    await _add_event(tenants["student_a"], tenants["skill_id"])
    await _add_event(tenants["student_b"], tenants["skill_id"])
    await _add_tenant_rows(tenants["student_a"], "a")
    await _add_tenant_rows(tenants["student_b"], "b")

    async with session_factory() as session:
        for table in TENANT_TABLES:
            visible_b = await _visible_user_ids(
                session, table, tenants["teacher_b"], "teacher"
            )
            assert visible_b == {tenants["student_b"]}, table

            visible_admin = await _visible_user_ids(session, table, None, "admin")
            assert {
                tenants["student_a"],
                tenants["student_b"],
            } <= visible_admin, table


async def test_http_request_uses_jwt_tenant_context(
    tenants, make_client, admin_client
):
    """Middleware прокидывает role/sub JWT в RLS-контекст HTTP-запроса."""
    await _add_tenant_rows(tenants["student_a"], "http")

    client = await make_client()
    _client, access, _uid = await login(client, tenants["email_b"])
    response = await client.get(
        f"{API}/admin/anticheat/students/{tenants['student_a']}/card",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["flags"] == []

    response = await admin_client.get(
        f"{API}/admin/anticheat/students/{tenants['student_a']}/card"
    )
    assert response.status_code == 200, response.text
    assert any(
        int(flag["userId"]) == tenants["student_a"]
        for flag in response.json()["flags"]
    )


async def test_rls_is_enabled_and_forced():
    """DoD: тест падает, если RLS отключить или снять FORCE."""
    async with session_factory() as session:
        rows = (
            await session.execute(
                sa.text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = ANY(:tables)"
                ),
                {"tables": list(TENANT_TABLES)},
            )
        ).all()
    flags = {str(name): (bool(enabled), bool(forced)) for name, enabled, forced in rows}
    assert set(flags) == set(TENANT_TABLES)
    assert all(enabled and forced for enabled, forced in flags.values()), flags
