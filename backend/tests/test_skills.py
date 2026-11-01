"""S-16: EMA-скоры — recalc, срезы, рекомендации, доступ."""

from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import select

from core.db import session_factory
from domains.cognitive import service as cognitive_svc
from domains.cognitive.models import Skill, SkillDomain, SkillEvent, UserSkillScore
from tests.conftest import API, login, register_verified


async def test_recalc_produces_scores_from_events(
    admin_client, make_client, unique_email
):
    client = await make_client()
    registered = await register_verified(client, unique_email)
    user_id = int(registered["id"])

    # события: passed (+1.0) и подсказка (−1.0)
    async with session_factory() as session:
        skills = (
            await session.execute(select(Skill).order_by(Skill.id))
        ).scalars().all()
        by_slug = {s.slug: s for s in skills}
        for slug, weight in (("functions", 1.0), ("conditions", -1.0)):
            session.add(
                SkillEvent(
                    user_id=user_id,
                    skill_id=by_slug[slug].id,
                    domain=SkillDomain.PYTHON,
                    weight=Decimal(str(weight)),
                    occurred_at=datetime.now(UTC),
                )
            )
        await session.commit()

    async with session_factory() as session:
        updated = await cognitive_svc.recalc_user_scores(session, user_id)
        await session.commit()
    assert updated >= 11  # реестр 11 навыков — срез на каждого

    async with session_factory() as session:
        rows = (
            await session.execute(
                sa.select(UserSkillScore).where(
                    UserSkillScore.user_id == user_id
                )
            )
        ).scalars().all()
        assert len(rows) >= 11
        assert all(0 <= float(s.score) <= 100 for s in rows)


async def test_skills_me_endpoint(admin_client, make_client, unique_email):
    _ = admin_client
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    response = await client.get(
        f"{API}/skills/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["skills"]) == 11  # реестр §10.1
    assert all(0 <= s["score"] <= 100 for s in body["skills"])


async def test_teacher_sees_student_slice(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, student_id = await login(client, unique_email)

    # student не может смотреть чужой срез
    response = await client.get(
        f"{API}/skills/{student_id}", headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 403

    # teacher — может
    from domains.auth.models import UserRole
    from tests.conftest import make_direct_user

    await make_direct_user(f"t-{unique_email}", role=UserRole.TEACHER)
    _c, teacher_access, _uid = await login(client, f"t-{unique_email}")
    response = await client.get(
        f"{API}/skills/{student_id}",
        headers={"Authorization": f"Bearer {teacher_access}"},
    )
    assert response.status_code == 200
    assert response.json()["userId"] == str(student_id)


async def test_recommendations_endpoint_shape(
    admin_client, make_client, unique_email
):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    response = await client.get(
        f"{API}/skills/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 200
    assert isinstance(response.json()["recommendations"], list)
