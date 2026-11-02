"""S-45: экспорт навыков/результатов (CSV и xAPI-совместимый payload)."""

import csv
import io
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select

from core.base import CamelModel
from domains.audit import service as audit_svc
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole
from domains.bot_lab.models import BotStats
from domains.cognitive import service as cognitive_svc
from domains.profile.models import UserProfile
from domains.progress.models import PyProgress

router = APIRouter(prefix="/admin/export", tags=["export"])

ReadRoles = Annotated[
    User,
    Depends(require_role(UserRole.TEACHER, UserRole.ADMIN, UserRole.AUDITOR)),
]


class XapiStatement(CamelModel):
    actor: dict
    verb: dict
    object: dict
    result: dict
    timestamp: str


class XapiOut(CamelModel):
    statements: list[XapiStatement]


async def _students(session):
    return (
        await session.execute(
            select(User, UserProfile)
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .where(User.role == UserRole.STUDENT)
            .order_by(User.id)
        )
    ).all()


@router.get("/skills.csv")
async def export_skills(
    request: Request,
    _guard: ReadRoles,
    session: DbSession,
) -> Response:
    rows = await _students(session)
    progress = {
        p.user_id: p
        for p in (await session.execute(select(PyProgress))).scalars()
    }
    stats = {
        s.user_id: s for s in (await session.execute(select(BotStats))).scalars()
    }
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "user_id",
            "email",
            "display_name",
            "level",
            "age_group",
            "skill_slug",
            "skill_title",
            "score",
            "week",
            "solved_count",
            "current_streak",
            "longest_streak",
            "elo",
            "wins",
            "losses",
            "draws",
        ]
    )
    for user, profile in rows:
        skills = await cognitive_svc.scores_snapshot(session, user.id)
        p = progress.get(user.id)
        s = stats.get(user.id)
        for skill in skills:
            writer.writerow(
                [
                    user.id,
                    user.email,
                    profile.display_name if profile else "",
                    profile.level.value if profile else "",
                    profile.age_group.value if profile else "unknown",
                    skill["slug"],
                    skill["titleRu"],
                    skill["score"],
                    skill["week"] or "",
                    p.solved_count if p else 0,
                    p.current_streak if p else 0,
                    p.longest_streak if p else 0,
                    float(s.elo) if s else 1000.0,
                    s.wins if s else 0,
                    s.losses if s else 0,
                    s.draws if s else 0,
                ]
            )
    await audit_svc.record(
        session,
        _guard,
        "export.skills",
        target_type="export",
        source="api",
        meta={"rows": len(rows)},
        request=request,
    )
    filename = f"skills-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/xapi", response_model=XapiOut)
async def export_xapi(
    request: Request,
    _guard: ReadRoles,
    session: DbSession,
) -> XapiOut:
    rows = await _students(session)
    stats = {
        s.user_id: s for s in (await session.execute(select(BotStats))).scalars()
    }
    now = datetime.now(UTC).isoformat()
    statements: list[XapiStatement] = []
    for user, profile in rows:
        actor = {
            "mbox": f"mailto:{user.email}",
            "name": profile.display_name if profile and profile.display_name else user.email,
        }
        for skill in await cognitive_svc.scores_snapshot(session, user.id):
            statements.append(
                XapiStatement(
                    actor=actor,
                    verb={
                        "id": "http://adlnet.gov/expapi/verbs/experienced",
                        "display": {"ru-RU": "изучил"},
                    },
                    object={
                        "id": f"https://chessclass.local/skills/{skill['slug']}",
                        "definition": {
                            "name": {"ru-RU": skill["titleRu"]},
                            "type": "https://chessclass.local/activity/skill",
                        },
                    },
                    result={
                        "score": {"scaled": round(float(skill["score"]) / 100, 4)},
                        "completion": True,
                    },
                    timestamp=now,
                )
            )
        s = stats.get(user.id)
        if s is not None:
            statements.append(
                XapiStatement(
                    actor=actor,
                    verb={
                        "id": "http://adlnet.gov/expapi/verbs/achieved",
                        "display": {"ru-RU": "достиг"},
                    },
                    object={
                        "id": f"https://chessclass.local/bots/{user.id}",
                        "definition": {
                            "name": {"ru-RU": "Рейтинг бота"},
                            "type": "https://chessclass.local/activity/bot-elo",
                        },
                    },
                    result={
                        "score": {
                            "raw": float(s.elo),
                            "min": 0,
                            "max": 3000,
                        },
                        "completion": True,
                    },
                    timestamp=now,
                )
            )
    await audit_svc.record(
        session,
        _guard,
        "export.xapi",
        target_type="export",
        source="api",
        meta={"statements": len(statements)},
        request=request,
    )
    return XapiOut(statements=statements)
