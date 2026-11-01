"""Seeds (Design §15.3, §10.1, §10.4): админ, демо-ученики, навыки, связи.

Идемпотентно: существующее пропускается. Запуск:
    python -m db.seeds
    docker compose -f docker-compose.dev.yml run --rm seed
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from core.config import settings
from core.db import session_factory
from core.levels import Level
from core.logging import setup_logging
from core.security import hash_password
from domains.auth.models import User, UserRole
from domains.auth.service import get_user_by_email
from domains.cognitive.models import Skill, SkillDomain, SkillLink
from domains.profile.models import UserProfile

logger = logging.getLogger(__name__)

# --- реестр навыков (Design §10.1): 11 навыков
SKILLS: tuple[dict[str, str], ...] = (
    {"slug": "loops_basic", "title": "Базовые циклы", "domain": "python",
     "description": "for/while, диапазоны, аккумуляторы"},
    {"slug": "loops_nested", "title": "Вложенные циклы", "domain": "python",
     "description": "матрицы, комбинаторика, инварианты цикла"},
    {"slug": "conditions", "title": "Ветвление", "domain": "python",
     "description": "if/elif/else, составные условия, границы"},
    {"slug": "functions", "title": "Функции и декомпозиция", "domain": "python",
     "description": "параметры, возвраты, разбиение задачи на шаги"},
    {"slug": "data_structures", "title": "Списки и словари", "domain": "python",
     "description": "индексация, ключи, выбор подходящей структуры"},
    {"slug": "debugging", "title": "Отладка", "domain": "python",
     "description": "чтение ошибок, отладочный вывод, тесты"},
    {"slug": "complexity", "title": "Сложность и оптимизация", "domain": "python",
     "description": "O-нотация, ускорение перебора, оценка объёма"},
    {"slug": "tactics_forks", "title": "Вилки и двойные удары", "domain": "chess",
     "description": "двойные атаки, удары по двум целям"},
    {"slug": "tactics_hanging", "title": "Висячие фигуры и угрозы", "domain": "chess",
     "description": "подвешенность, считаем атаку/защиту"},
    {"slug": "calculation", "title": "Расчёт вариантов", "domain": "chess",
     "description": "глубина расчёта, дерево вариантов, кандидат-ходы"},
    {"slug": "planning", "title": "План и структура партии", "domain": "chess",
     "description": "стратегия, слабости, долгосрочный план"},
)

# --- кросс-доменные связи (Design §10.4): python → chess
SKILL_LINKS: tuple[tuple[str, str, float], ...] = (
    ("loops_nested", "tactics_forks", 1.0),
    ("conditions", "tactics_hanging", 1.0),
    ("functions", "planning", 1.0),
    ("debugging", "calculation", 1.0),
    ("complexity", "calculation", 1.0),
)


async def _ensure_user(
    session,
    email: str,
    password: str,
    role: UserRole,
    level: Level,
    display_name: str,
) -> bool:
    if await get_user_by_email(session, email) is not None:
        return False
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=role,
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    session.add(UserProfile(user_id=user.id, level=level, display_name=display_name))
    await session.flush()
    logger.info("seeds: создан %s %s", role.value, email)
    return True


async def seed_users(session) -> dict[str, int]:
    created = 0
    created += await _ensure_user(
        session, settings.seed_admin_email, settings.seed_admin_password,
        UserRole.ADMIN, Level.NOVICE, "Админ ChessClass",
    )
    created += await _ensure_user(
        session, "teacher@chessclass.dev", settings.seed_teacher_password,
        UserRole.TEACHER, Level.INTERMEDIATE, "Учитель ChessClass",
    )
    created += await _ensure_user(
        session, "auditor@chessclass.dev", settings.seed_auditor_password,
        UserRole.AUDITOR, Level.NOVICE, "Аудитор ChessClass",
    )
    for name, level in (
        ("student1", Level.NOVICE),
        ("student2", Level.INTERMEDIATE),
    ):
        created += await _ensure_user(
            session, f"{name}@chessclass.dev", settings.seed_student_password,
            UserRole.STUDENT, level, f"Ученик {name[-1]}",
        )
    return {"users": created}


async def seed_skills(session) -> dict[str, int]:
    existing = set((await session.execute(select(Skill.slug))).scalars())
    created = 0
    for item in SKILLS:
        if item["slug"] in existing:
            continue
        session.add(
            Skill(
                slug=item["slug"],
                title_ru=item["title"],
                domain=SkillDomain(item["domain"]),
                domain_ref={"description": item["description"]},
            )
        )
        created += 1
    await session.flush()
    return {"skills": created}


async def seed_skill_links(session) -> dict[str, int]:
    id_by_slug = dict((await session.execute(select(Skill.slug, Skill.id))).all())
    existing = set(
        (await session.execute(select(SkillLink.from_skill_id, SkillLink.to_skill_id))).all()
    )
    created = 0
    for from_slug, to_slug, weight in SKILL_LINKS:
        pair = (id_by_slug[from_slug], id_by_slug[to_slug])
        if pair in existing:
            continue
        session.add(
            SkillLink(from_skill_id=pair[0], to_skill_id=pair[1], weight=weight)
        )
        created += 1
    await session.flush()
    return {"skill_links": created}


async def run() -> dict[str, int]:
    async with session_factory() as session:
        stats: dict[str, int] = {}
        for step in (seed_users, seed_skills, seed_skill_links):
            stats.update(await step(session))
        await session.commit()
    from db.seeds_rag import seed_rag
    from db.seeds_tasks import seed_tasks

    async with session_factory() as session:
        stats.update(await seed_tasks(session))
        await session.commit()
    async with session_factory() as session:
        stats.update(await seed_rag(session))
        await session.commit()
    return stats


def main() -> None:
    setup_logging("INFO")
    stats = asyncio.run(run())
    logger.info("seeds: готово %s", stats)


if __name__ == "__main__":
    main()
