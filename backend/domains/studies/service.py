"""S-43: генерация этюдов (SF + LLM), ревью и попытки решения."""

import logging
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import chess
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from core.levels import Level
from domains.audit import service as audit_svc
from domains.auth.models import User, UserRole
from domains.chess_lab.service import run_engine_analysis
from domains.studies.models import ChessStudy, StudyStatus
from llm.gateway import LLMCallContext, llm_generate
from llm.prompts.builder import build_messages

logger = logging.getLogger(__name__)

#: Курируемые позиции-кандидаты: генератор выбирает одну, SF проверяет
#: легальность/лучший ход, LLM пишет условие. Так v0.2 не зависит от
#: случайного «пустого» playout и остаётся воспроизводимым.
STUDY_CANDIDATES: tuple[dict[str, str], ...] = (
    {
        "fen": "r1bq1rk1/ppp2ppp/2n2n2/3pp3/8/2NBPN2/PPP2PPP/R1BQ1RK1 w - - 0 20",
        "theme": "planning",
        "difficulty": "intermediate",
        "title": "План в миттельшпиле",
    },
    {
        "fen": "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1",
        "theme": "tactics",
        "difficulty": "novice",
        "title": "Найди лучший ход",
    },
    {
        "fen": "r3k2r/ppp2ppp/2n5/3q4/8/2N5/PPP2PPP/R2QK2R w KQkq - 0 12",
        "theme": "tactics",
        "difficulty": "intermediate",
        "title": "Активность фигур",
    },
    {
        "fen": "8/8/8/3k4/8/3K4/8/7R w - - 0 1",
        "theme": "endgame",
        "difficulty": "novice",
        "title": "Ладейный эндшпиль",
    },
    {
        "fen": "2r3k1/5ppp/8/8/8/8/5PPP/2R3K1 w - - 0 1",
        "theme": "endgame",
        "difficulty": "intermediate",
        "title": "Ладьи и пешки",
    },
    {
        "fen": "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1",
        "theme": "endgame",
        "difficulty": "novice",
        "title": "Король и пешка",
    },
    {
        "fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        "theme": "opening",
        "difficulty": "novice",
        "title": "Дебютный план",
    },
    {
        "fen": "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 6",
        "theme": "opening",
        "difficulty": "intermediate",
        "title": "Развитие и центр",
    },
)

AnalyzeFn = Callable[[str, Level], Awaitable[list[dict]]]
GenerateTextFn = Callable[[], Awaitable[str]]


async def _default_analyze(fen: str, level: Level) -> list[dict]:
    return await run_engine_analysis(fen, level)


async def generate_study(
    session: AsyncSession,
    redis,
    user: User,
    *,
    candidate_index: int | None = None,
    analyze: AnalyzeFn | None = None,
    generate_text: GenerateTextFn | None = None,
) -> ChessStudy:
    """Сгенерировать черновик: SF-валидация + LLM-условие."""
    since = datetime.now(UTC) - timedelta(days=1)
    recent = int(
        await session.scalar(
            select(func.count())
            .select_from(ChessStudy)
            .where(
                ChessStudy.created_by == user.id,
                ChessStudy.created_at >= since,
            )
        )
        or 0
    )
    if recent >= settings.study_daily_limit:
        raise AppError(
            "study_limit",
            f"Лимит генерации этюдов: {settings.study_daily_limit}/сутки",
            429,
        )

    index = (
        candidate_index
        if candidate_index is not None
        else random.randrange(len(STUDY_CANDIDATES))
    )
    candidate = STUDY_CANDIDATES[index % len(STUDY_CANDIDATES)]
    board = chess.Board(candidate["fen"])
    analyzer = analyze or _default_analyze
    try:
        lines = await analyzer(candidate["fen"], Level.INTERMEDIATE)
    except Exception as exc:  # noqa: BLE001 - генерация без SF не публикуется
        logger.warning("studies: SF validation failed: %s", exc)
        raise AppError(
            "study_generation_failed", "Не удалось проверить позицию SF", 502
        ) from exc

    top = lines[0] if lines else None
    if top is None:
        raise AppError("study_generation_failed", "SF не вернул линию", 502)
    solution_uci = str(top["move_uci"])
    if solution_uci not in {move.uci() for move in board.legal_moves}:
        raise AppError(
            "study_generation_failed", "SF вернул нелегальный ход", 502
        )
    solution_line = list(top.get("pv") or [solution_uci])

    condition = ""
    if generate_text is not None:
        condition = await generate_text()
    else:
        messages = build_messages(
            "chess_lab.study",
            Level.INTERMEDIATE,
            request="Сформулируй короткое условие шахматного этюда.",
            facts=[
                f"FEN: {candidate['fen']}",
                f"Тема: {candidate['theme']}",
                f"Сложность: {candidate['difficulty']}",
                f"Лучший ход (SF): {solution_uci}",
            ],
        )
        result = await llm_generate(
            session,
            redis,
            route="chess_lab.study",
            level=Level.INTERMEDIATE,
            messages=messages,
            ctx=LLMCallContext(user_id=user.id, billing_tier="free"),
        )
        condition = result.text

    study = ChessStudy(
        title=candidate["title"],
        fen=candidate["fen"],
        condition_text=(
            condition.strip()
            or "Найди лучший ход за сторону, которая ходит."
        ),
        theme=candidate["theme"],
        difficulty=candidate["difficulty"],
        solution_uci=solution_uci,
        solution_line=solution_line,
        status=StudyStatus.DRAFT,
        source="generated",
        generator_meta={
            "candidateIndex": index,
            "engine": top,
        },
        created_by=user.id,
    )
    session.add(study)
    await session.flush()
    await audit_svc.record(
        session,
        user,
        "studies.generate",
        target_type="study",
        target_id=study.id,
        meta={"theme": study.theme, "difficulty": study.difficulty},
    )
    return study


async def _get_study(session: AsyncSession, study_id: int) -> ChessStudy:
    study = await session.get(ChessStudy, study_id)
    if study is None:
        raise AppError("study_not_found", "Этюд не найден", 404)
    return study


def _can_manage(user: User, study: ChessStudy) -> bool:
    return user.role is UserRole.ADMIN or study.created_by == user.id


async def submit_for_review(
    session: AsyncSession, user: User, study_id: int
) -> ChessStudy:
    study = await _get_study(session, study_id)
    if user.role is not UserRole.ADMIN and not _can_manage(user, study):
        raise AppError("study_forbidden", "Нет доступа к этюду", 403)
    if study.status is not StudyStatus.DRAFT:
        raise AppError("study_state_invalid", "Этюд не в черновике", 409)
    study.status = StudyStatus.REVIEW
    await session.flush()
    await audit_svc.record(
        session,
        user,
        "studies.submit",
        target_type="study",
        target_id=study.id,
    )
    return study


async def review_study(
    session: AsyncSession,
    user: User,
    study_id: int,
    *,
    decision: str,
    note: str | None,
) -> ChessStudy:
    if user.role not in (UserRole.TEACHER, UserRole.ADMIN):
        raise AppError("study_forbidden", "Ревью доступно учителю", 403)
    study = await _get_study(session, study_id)
    if study.status is not StudyStatus.REVIEW:
        raise AppError("study_state_invalid", "Этюд не на ревью", 409)
    study.status = (
        StudyStatus.PUBLISHED if decision == "approve" else StudyStatus.REJECTED
    )
    study.reviewed_by = user.id
    study.reviewed_at = datetime.now(UTC)
    study.review_note = note
    await session.flush()
    await audit_svc.record(
        session,
        user,
        "studies.review",
        target_type="study",
        target_id=study.id,
        meta={"decision": decision, "note": note},
    )
    return study


async def list_studies(
    session: AsyncSession,
    *,
    status: StudyStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ChessStudy], int]:
    stmt = select(ChessStudy)
    if status is not None:
        stmt = stmt.where(ChessStudy.status == status)
    total = int(
        await session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        or 0
    )
    rows = (
        await session.execute(
            stmt.order_by(ChessStudy.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), total


async def get_published(session: AsyncSession, study_id: int) -> ChessStudy:
    study = await _get_study(session, study_id)
    if study.status is not StudyStatus.PUBLISHED:
        raise AppError("study_not_found", "Этюд не найден", 404)
    return study


async def attempt_study(
    session: AsyncSession,
    user: User,
    study_id: int,
    move_uci: str,
) -> dict:
    study = await get_published(session, study_id)
    board = chess.Board(study.fen)
    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError as exc:
        raise AppError("study_invalid_move", "Некорректный ход", 422) from exc
    if move not in board.legal_moves:
        raise AppError("study_invalid_move", "Ход нелегален", 422)
    correct = move_uci == study.solution_uci
    await audit_svc.record(
        session,
        user,
        "studies.attempt",
        target_type="study",
        target_id=study.id,
        meta={"correct": correct},
    )
    return {
        "correct": correct,
        "message": (
            "Верно! Это лучший ход."
            if correct
            else "Пока не лучший ход — попробуй ещё."
        ),
        "nextUci": study.solution_line[1] if correct and len(study.solution_line) > 1 else None,
    }
