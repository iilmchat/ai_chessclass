"""Генерация PDF-отчёта родителю (порт идеи app/export/pdf из annotator).

Шрифт — системный TTF с кириллицей (DejaVuSans в контейнере; путь —
`REPORTS_FONT_PATH`). Абзацы родителям — только из фактов (EMA-скоры,
Elo, счёт матчей); проза — по маршруту reports.parent_summary (S-25).
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from fpdf import FPDF
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from domains.bot_lab.models import BotStats
from domains.cognitive import service as cognitive_svc
from domains.reports.models import ReportPdf

logger = logging.getLogger(__name__)


def build_pdf(
    *,
    student_email: str,
    scores: list[dict],
    elo: float,
    wins: int,
    losses: int,
    draws: int,
) -> bytes:
    """Собрать PDF: заголовок, сводка навыков, Elo бота."""
    font_path = Path(settings.reports_font_path)
    if not font_path.is_file():
        raise AppError(
            "pdf_font_unavailable",
            f"Шрифт не найден: {font_path} (DejaVuSans в образе)",
            500,
        )

    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", str(font_path))
    pdf.set_font("DejaVu", size=16)
    pdf.cell(text="Отчёт для родителей — ChessClass", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=10)
    pdf.cell(
        text=f"Ученик: {student_email} · {datetime.now().strftime('%Y-%m-%d')}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)

    pdf.set_font("DejaVu", size=13)
    pdf.cell(text="Навыки (0–100)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=11)
    for s in scores:
        pdf.cell(
            text=f"• {s['titleRu']}: {s['score']}", new_x="LMARGIN", new_y="NEXT"
        )
    pdf.ln(4)

    pdf.set_font("DejaVu", size=13)
    pdf.cell(text="Шахматный бот", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=11)
    pdf.cell(
        text=f"Elo: {elo} · победы {wins} · поражения {losses} · ничьи {draws}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    return bytes(pdf.output())


async def generate_for_student(
    session: AsyncSession, requester, student_id: int
) -> dict:
    """Генерация + сохранение PDF на volume; запись в reports_pdfs."""
    from domains.auth.models import User

    student = await session.get(User, student_id)
    if student is None:
        raise AppError("user_not_found", "Ученик не найден", 404)

    scores = await cognitive_svc.scores_snapshot(session, student_id)
    stats = await session.get(BotStats, student_id)
    elo = float(stats.elo) if stats is not None else 1000.0
    wins = stats.wins if stats is not None else 0
    losses = stats.losses if stats is not None else 0
    draws = stats.draws if stats is not None else 0

    pdf_bytes = build_pdf(
        student_email=student.email,
        scores=scores,
        elo=elo,
        wins=wins,
        losses=losses,
        draws=draws,
    )

    out_dir = Path(settings.reports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"report-{student_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.pdf"
    out_path = out_dir / filename
    out_path.write_bytes(pdf_bytes)

    record = ReportPdf(
        student_id=student_id,
        requested_by=requester.id,
        kind="parent",
        path=str(out_path),
        size_bytes=len(pdf_bytes),
    )
    session.add(record)
    await session.flush()
    logger.info("reports: PDF %s (%d байт)", out_path, len(pdf_bytes))
    return {"reportId": record.id, "path": str(out_path), "sizeBytes": len(pdf_bytes)}
