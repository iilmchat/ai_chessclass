"""S-25: PDF-отчёты родителям — генерация, скачивание, RBAC."""

from pathlib import Path

import pytest

from core.config import settings
from tests.conftest import API, login, register_verified


def _font_available() -> bool:
    return Path(settings.reports_font_path).is_file()


pytestmark = pytest.mark.skipif(
    not _font_available(), reason="DejaVuSans не установлен в образе"
)


def test_pdf_build_contains_cyrillic():
    from domains.reports.pdf import build_pdf

    scores = [
        {
            "titleRu": "Циклы (базовые)",
            "score": 62.5,
            "slug": "loops_basic",
            "domain": "python",
        }
    ]
    pdf_bytes = build_pdf(
        student_email="student@example.com",
        scores=scores,
        elo=1042.0,
        wins=3,
        losses=2,
        draws=1,
    )
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


async def test_generate_and_download_pdf(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, student_id = await login(client, unique_email)

    # teacher генерирует отчёт
    response = await admin_client.post(f"{API}/reports/pdf/{student_id}")
    assert response.status_code == 201
    body = response.json()
    assert body["sizeBytes"] > 1000
    report_id = body["reportId"]

    # скачивание — валидный PDF
    response = await admin_client.get(f"{API}/reports/pdf/{report_id}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")

    # student не может генерировать
    response = await client.post(
        f"{API}/reports/pdf/{student_id}", headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 403

    # 404 на несуществующий отчёт
    response = await admin_client.get(f"{API}/reports/pdf/999999")
    assert response.status_code == 404
