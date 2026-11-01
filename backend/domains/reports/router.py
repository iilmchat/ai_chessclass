"""Роутер /api/v1/reports (Design §12.2): PDF родителям (teacher)."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from core.errors import AppError
from domains.audit import service as audit_svc
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole

router = APIRouter(prefix="/reports", tags=["reports"])


def _teacher() -> User:
    """Фабрика зависимости (require_role), используется в Depends ниже."""
    raise NotImplementedError


TeacherOrAdmin = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]
AuditorOrTeacher = Annotated[
    User,
    Depends(require_role(UserRole.TEACHER, UserRole.ADMIN, UserRole.AUDITOR)),
]


@router.post("/pdf/{student_id}", status_code=201)
async def generate_pdf(
    student_id: int,
    requester: TeacherOrAdmin,
    session: DbSession,
    request: Request,
) -> dict:
    from domains.reports import pdf as pdf_svc

    result = await pdf_svc.generate_for_student(session, requester, student_id)
    await audit_svc.record(
        session,
        requester,
        "reports.pdf.generate",
        target_type="user",
        target_id=student_id,
        meta={"reportId": str(result["reportId"])},
        request=request,
    )
    return {"reportId": str(result["reportId"]), "sizeBytes": result["sizeBytes"]}


@router.get("/pdf/{report_id}")
async def download_pdf(
    report_id: int,
    _guard: AuditorOrTeacher,
    session: DbSession,
    request: Request,
) -> Response:
    from domains.reports.models import ReportPdf

    record = await session.get(ReportPdf, report_id)
    if record is None:
        raise AppError("report_not_found", "Отчёт не найден", 404)
    path = Path(record.path)
    if not path.is_file():
        raise AppError("report_file_missing", "Файл отчёта не найден на диске", 404)
    await audit_svc.record(
        session,
        _guard,
        "reports.pdf.download",
        target_type="report",
        target_id=report_id,
        meta={"studentId": str(record.student_id)},
        request=request,
    )
    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )
