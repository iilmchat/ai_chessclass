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


def _playout_candidate() -> dict[str, str]:
    """Случайный playout из начальной позиции (S-53)."""
    board = chess.Board()
    for _ in range(random.randint(8, 30)):
        moves = list(board.legal_moves)
        if not moves or board.is_game_over():
            break
        board.push(random.choice(moves))
    if board.is_game_over():
        return dict(STUDY_CANDIDATES[random.randrange(len(STUDY_CANDIDATES))])
    return {
        "fen": board.fen(),
        "theme": "tactics",
        "difficulty": "intermediate",
        "title": f"Плейаут #{random.randint(100, 999)}",
    }


def _pick_candidate(
    candidate_index: int | None, exclude_fens: set[str]
) -> tuple[int, dict[str, str]]:
    if candidate_index is not None:
        index = candidate_index % len(STUDY_CANDIDATES)
        return index, dict(STUDY_CANDIDATES[index])
    for _ in range(30):
        index = random.randrange(len(STUDY_CANDIDATES))
        candidate = STUDY_CANDIDATES[index]
        if candidate["fen"] not in exclude_fens:
            return index, dict(candidate)
    for extra in range(50):
        candidate = _playout_candidate()
        if candidate["fen"] not in exclude_fens:
            return len(STUDY_CANDIDATES) + extra, candidate
    raise AppError(
        "study_generation_failed", "Не удалось подобрать уникальную позицию", 502
    )


def _auto_review_issues(
    fen: str, solution_uci: str, solution_line: list[str]
) -> list[str]:
    issues: list[str] = []
    try:
        board = chess.Board(fen)
    except ValueError:
        return ["invalid_fen"]
    line = solution_line or [solution_uci]
    for index, uci in enumerate(line):
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            issues.append(f"invalid_uci:{index}")
            break
        if move not in board.legal_moves:
            issues.append(f"illegal_uci:{index}")
            break
        board.push(move)
    return issues


def _difficulty_from_engine(top: dict) -> str:
    score = top.get("score_cp")
    if score is None:
        return "advanced"
    value = abs(int(score))
    if value >= 250:
        return "novice"
    if value >= 80:
        return "intermediate"
    return "advanced"



async def _default_analyze(fen: str, level: Level) -> list[dict]:
    return await run_engine_analysis(fen, level)


async def generate_study(
    session: AsyncSession,
    redis,
    user: User,
    *,
    candidate_index: int | None = None,
    exclude_fens: set[str] | None = None,
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

    index, candidate = _pick_candidate(candidate_index, exclude_fens or set())
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
    auto_issues = _auto_review_issues(
        candidate["fen"], solution_uci, solution_line
    )
    difficulty = _difficulty_from_engine(top)

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
        difficulty=difficulty,
        solution_uci=solution_uci,
        solution_line=solution_line,
        status=StudyStatus.DRAFT if not auto_issues else StudyStatus.REJECTED,
        source="generated",
        generator_meta={
            "candidateIndex": index,
            "engine": top,
            "engineDifficulty": difficulty,
            "autoReview": {
                "ok": not auto_issues,
                "issues": auto_issues,
            },
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


async def generate_batch(
    session: AsyncSession,
    redis,
    user: User,
    *,
    count: int,
    analyze: AnalyzeFn | None = None,
    generate_text: GenerateTextFn | None = None,
) -> dict:
    """Батч-генерация с дедупликацией FEN и метриками брака (S-53)."""
    if not 1 <= count <= 20:
        raise AppError("study_batch_invalid", "count: 1..20", 422)
    created: list[ChessStudy] = []
    skipped = 0
    defects = 0
    fens: set[str] = set()
    for _ in range(count):
        try:
            study = await generate_study(
                session,
                redis,
                user,
                exclude_fens=fens,
                analyze=analyze,
                generate_text=generate_text,
            )
        except AppError as exc:
            if exc.code == "study_limit":
                break
            raise
        if study.fen in fens:
            skipped += 1
            continue
        fens.add(study.fen)
        created.append(study)
        if study.status is StudyStatus.REJECTED:
            defects += 1
    requested = count
    return {
        "requested": requested,
        "created": created,
        "skipped": skipped,
        "defects": defects,
        "defectRate": round(defects / requested, 3) if requested else 0.0,
        "uniqueFens": len(fens),
    }


async def generator_metrics(session: AsyncSession) -> dict:
    rows = list(
        (
            await session.execute(
                select(ChessStudy).where(ChessStudy.source == "generated")
            )
        ).scalars()
    )
    reviewed = [
        row
        for row in rows
        if isinstance((row.generator_meta or {}).get("autoReview"), dict)
    ]
    defects = sum(
        1
        for row in reviewed
        if not (row.generator_meta or {}).get("autoReview", {}).get("ok", True)
    )
    fens = [row.fen for row in rows]
    return {
        "generated": len(rows),
        "autoReviewed": len(reviewed),
        "defects": defects,
        "defectRate": round(defects / len(reviewed), 3) if reviewed else 0.0,
        "duplicateFens": len(fens) - len(set(fens)),
    }


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


async def attempt_line(
    session: AsyncSession,
    user: User,
    study_id: int,
    moves: list[str],
) -> dict:
    """Проверить многоходовую линию/префикс PV (S-53)."""
    study = await get_published(session, study_id)
    if not moves:
        raise AppError("study_invalid_line", "Нужна хотя бы один ход", 422)
    line = list(study.solution_line or [study.solution_uci])
    board = chess.Board(study.fen)
    for index, uci in enumerate(moves):
        if index >= len(line) or uci != line[index]:
            await audit_svc.record(
                session,
                user,
                "studies.attempt_line",
                target_type="study",
                target_id=study.id,
                meta={"correct": False, "failedPly": index},
            )
            return {
                "correct": False,
                "failedPly": index,
                "message": f"На ходе {index + 1} линия расходится с решением.",
                "nextUci": line[index] if index < len(line) else None,
            }
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as exc:
            raise AppError("study_invalid_move", "Некорректный ход", 422) from exc
        if move not in board.legal_moves:
            raise AppError("study_invalid_move", "Ход нелегален", 422)
        board.push(move)
    next_uci = line[len(moves)] if len(moves) < len(line) else None
    await audit_svc.record(
        session,
        user,
        "studies.attempt_line",
        target_type="study",
        target_id=study.id,
        meta={"correct": True, "plies": len(moves)},
    )
    return {
        "correct": True,
        "failedPly": None,
        "message": "Линия верна." if next_uci is None else "Верно, продолжайте линию.",
        "nextUci": next_uci,
    }
