"""Плагиат и профиль-сверка (S-24, §9.2).

plagiarism_suspected: сходство кода сдачи с эталоном/другими учениками
(hash-эмбеддер через RAG-инфраструктуру + косинус; §9.3 «embeddings 768 +
l2-метрики»).
profile_mismatch: кросс-доменная сверка (advanced-шахматы при
novice-циклах; бот 1600 при basic-коде) — по EMA-скорам.
"""

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domains.anticheat.models import FlagDomain, FlagKind
from domains.anticheat.service import record_flag
from domains.cognitive.models import UserSkillScore
from domains.python_teacher.models import PyReferenceSolution, PySubmission
from rag.embeddings import hash_embedding

logger = logging.getLogger(__name__)

#: порог сходства с эталоном/сверстником → флаг (§9.2)
PLAGIARISM_SIMILARITY_THRESHOLD = 0.95


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


async def check_plagiarism(
    session: AsyncSession,
    *,
    user_id: int,
    submission_id: int,
    assignment_id: int,
    code: str,
) -> None:
    """Сравнить код сдачи с эталоном и другими сдачами по этому заданию."""
    refs = (
        await session.execute(
            select(PyReferenceSolution).where(
                PyReferenceSolution.assignment_id == assignment_id
            )
        )
    ).scalars().all()
    others = (
        await session.execute(
            select(PySubmission)
            .where(
                PySubmission.assignment_id == assignment_id,
                PySubmission.user_id != user_id,
            )
            .order_by(PySubmission.id.desc())
            .limit(20)
        )
    ).scalars().all()

    vec = hash_embedding(code)
    matches: list[dict] = []
    for ref in refs:
        similarity = _cosine(vec, hash_embedding(ref.source))
        matches.append({"ref": "reference", "similarity": round(similarity, 4)})
    for other in others:
        if other.code == code:
            matches.append(
                {"ref": f"submission:{other.id}", "similarity": 1.0}
            )
            continue
        similarity = _cosine(vec, hash_embedding(other.code))
        if similarity >= PLAGIARISM_SIMILARITY_THRESHOLD:
            matches.append(
                {"ref": f"submission:{other.id}", "similarity": round(similarity, 4)}
            )

    max_similarity = max((m["similarity"] for m in matches), default=0.0)
    if max_similarity < PLAGIARISM_SIMILARITY_THRESHOLD:
        return
    await record_flag(
        session,
        user_id=user_id,
        kind=FlagKind.PLAGIARISM_SUSPECTED,
        domain=FlagDomain.PYTHON,
        confidence=Decimal(str(min(1.0, max_similarity))).quantize(Decimal("0.01")),
        evidence={
            "submissionId": submission_id,
            "matches": matches[:10],
            "threshold": PLAGIARISM_SIMILARITY_THRESHOLD,
        },
        source_ref=f"py_submission:{submission_id}",
    )


async def check_profile_mismatch(
    session: AsyncSession, user_id: int
) -> None:
    """Кросс-доменная сверка (§9.2): advanced-шахматы при novice-циклах.

    Сравниваем EMA-скоры навыков-представителей доменов: chess ≥ 70 при
    python-циклы < 40 → флаг (это и есть кросс-валидация экосистемы).
    """
    scores = {
        row.skill_id: float(row.score)
        for row in (
            await session.execute(
                select(UserSkillScore).where(UserSkillScore.user_id == user_id)
            )
        ).scalars()
    }
    if not scores:
        return

    from domains.cognitive.models import Skill

    slug_by_id = {
        s.id: s.slug
        for s in (await session.execute(select(Skill))).scalars()
    }
    chess_score = next(
        (v for k, v in scores.items() if slug_by_id.get(k) == "tactics_forks"),
        None,
    )
    python_score = next(
        (v for k, v in scores.items() if slug_by_id.get(k) == "loops_basic"),
        None,
    )
    if chess_score is None or python_score is None:
        return
    if chess_score >= 70 and python_score < 40:
        await record_flag(
            session,
            user_id=user_id,
            kind=FlagKind.PROFILE_MISMATCH,
            domain=FlagDomain.CROSS,
            confidence=Decimal("0.65"),
            evidence={
                "chessScore": chess_score,
                "pythonLoopsScore": python_score,
                "note": "advanced-шахматы при novice-циклах (§9.2)",
            },
            source_ref="profile",
        )
