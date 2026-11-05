"""LLM-judge (S-23, §9.3): сессии «объясни свой код/ход» через Decider.

Транскрипт хранится (anticheat_judge_sessions); вердикт — за учителем
(ADR-005). Маршрут anticheat.judge_explain (judge-тир, короткие ответы).
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.errors import AppError
from core.levels import Level
from domains.anticheat.models import JudgeSession
from domains.profile.models import UserProfile
from llm.gateway import LLMCallContext, llm_generate
from llm.prompts.builder import build_messages

logger = logging.getLogger(__name__)


async def start_judge_session(
    session: AsyncSession,
    redis,
    user,
    *,
    source_ref: str,
    question: str,
    student_code: str | None = None,
) -> dict:
    """Сессия «объясни свой код/ход»: вопрос ученику → ответ Decider-judge.

    question — объяснение ученика (что делает его код). Judge просит
    уточнить/объяснить ещё раз — без подсказки решения (§9.3).
    """
    profile = await session.get(UserProfile, user.id)
    level = profile.level if profile is not None else Level.NOVICE
    tier = profile.billing_tier.value if profile is not None else "free"

    # S-71: вопрос и код ученика — untrusted-данные, а не trusted facts.
    user_input = f"Ученик объясняет свой код/ход: «{question[:1000]}»"
    if student_code:
        user_input += f"\nКод ученика (не показывать ученику дословно):\n{student_code[:1500]}"

    messages = build_messages(
        "anticheat.judge_explain",
        level,
        request="Задай 1–2 уточняющих вопроса, чтобы проверить понимание.",
        user_input=user_input,
    )
    result = await llm_generate(
        session,
        redis,
        route="anticheat.judge_explain",
        level=level,
        messages=messages,
        ctx=LLMCallContext(user_id=user.id, billing_tier=tier),
    )

    judge_session = JudgeSession(
        user_id=user.id,
        source_ref=source_ref,
        question=question[:2000],
        answer=result.text,
        model_used=result.model_used,
        transcript=[{"role": m.role, "content": m.content} for m in messages],
    )
    session.add(judge_session)
    await session.flush()

    return {
        "sessionId": judge_session.id,
        "question": judge_session.question,
        "answer": result.text,
        "modelUsed": result.model_used,
    }


async def list_sessions(
    session: AsyncSession, teacher, *, user_id: int | None = None, limit: int = 50
) -> list[JudgeSession]:
    stmt = select(JudgeSession).order_by(JudgeSession.id.desc()).limit(limit)
    if user_id is not None:
        stmt = stmt.where(JudgeSession.user_id == user_id)
    return list((await session.execute(stmt)).scalars().all())


async def review_session(
    session: AsyncSession, teacher, session_id: int, verdict: str
) -> JudgeSession:
    judge_session = await session.get(JudgeSession, session_id)
    if judge_session is None:
        raise AppError("session_not_found", "Judge-сессия не найдена", 404)
    judge_session.teacher_verdict = verdict
    judge_session.reviewed_by = teacher.id
    from datetime import UTC, datetime

    judge_session.reviewed_at = datetime.now(UTC)
    await session.flush()
    return judge_session
