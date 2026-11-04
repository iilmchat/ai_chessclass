"""S-54: RAG-редактор — draft/publish/версии/откат/импорт/eval."""

import base64
import uuid

import sqlalchemy as sa

from core.db import session_factory
from rag.models import RagChunk, RagDocument, RagDocumentVersion
from tests.conftest import API


def _title() -> str:
    return f"RAG редактор {uuid.uuid4().hex[:8]}"


def _token() -> str:
    """Уникальный токен: hash-векторы идентичных текстов «засоряют» top-k
    при повторе теста в одной dev-БД (S-67: тестовая гигиена)."""
    return uuid.uuid4().hex[:12]


async def test_rag_editor_publish_versions_rollback(admin_client):
    title = _title()
    token = _token()
    document_id = None
    try:
        response = await admin_client.post(
            f"{API}/admin/rag/documents",
            json={
                "titleRu": title,
                "source": "unit-test",
                "domain": "general",
                "kind": "explanation",
                "text": f"Уникальное понятие {token} квантовый ферзь объясняет стратегию.",
                "license": "CC-BY-4.0",
            },
        )
        assert response.status_code == 201, response.text
        doc = response.json()
        assert doc["status"] == "draft"
        assert doc["version"] == 1
        assert doc["license"] == "CC-BY-4.0"
        document_id = doc["id"]

        response = await admin_client.get(
            f"{API}/admin/rag/search", params={"q": "квантовый ферзь", "k": 5}
        )
        assert response.status_code == 200
        assert all(hit["documentId"] != document_id for hit in response.json()["hits"])

        response = await admin_client.post(
            f"{API}/admin/rag/documents/{document_id}/publish"
        )
        assert response.status_code == 200, response.text
        response = await admin_client.get(
            f"{API}/admin/rag/search", params={"q": token, "k": 5}
        )
        assert response.status_code == 200
        assert any(hit["documentId"] == document_id for hit in response.json()["hits"])

        response = await admin_client.patch(
            f"{API}/admin/rag/documents/{document_id}",
            json={"text": f"Новая версия: {token} и пешечная структура."},
        )
        assert response.status_code == 200, response.text
        assert response.json()["version"] == 2
        assert response.json()["status"] == "draft"

        response = await admin_client.get(
            f"{API}/admin/rag/documents/{document_id}/versions"
        )
        assert response.status_code == 200
        versions = response.json()
        assert {row["version"] for row in versions} == {1, 2}
        assert versions[-1]["license"] == "CC-BY-4.0"

        response = await admin_client.post(
            f"{API}/admin/rag/documents/{document_id}/rollback/1"
        )
        assert response.status_code == 200, response.text
        assert response.json()["version"] == 3
        assert "квантовый ферзь объясняет" in response.json()["text"]
        assert response.json()["status"] == "published"

        response = await admin_client.get(f"{API}/admin/rag/eval")
        assert response.status_code == 200
        assert response.json()["passed"] is True
    finally:
        if document_id is not None:
            document_id_int = int(document_id)
            async with session_factory() as session:
                await session.execute(
                    sa.delete(RagChunk).where(
                        RagChunk.document_id == document_id_int
                    )
                )
                await session.execute(
                    sa.delete(RagDocumentVersion).where(
                        RagDocumentVersion.document_id == document_id_int
                    )
                )
                await session.execute(
                    sa.delete(RagDocument).where(
                        RagDocument.id == document_id_int
                    )
                )
                await session.commit()


async def test_eval_gold_set_min_20_cases(admin_client):
    """S-64: gold-set eval — ≥ 20 кейсов с деталями (результат по каждому)."""
    response = await admin_client.get(f"{API}/admin/rag/eval")
    assert response.status_code == 200
    body = response.json()
    assert body["cases"] >= 20
    assert len(body["results"]) == body["cases"]
    assert {case["order"] for case in body["results"]} == set(
        range(1, body["cases"] + 1)
    )
    assert all(
        isinstance(case["vectorHit"], bool)
        and isinstance(case["hybridHit"], bool)
        and case["query"]
        for case in body["results"]
    )
    assert isinstance(body["passed"], bool)


async def test_rag_import_markdown_and_pdf(admin_client):
    markdown = "# План\n\nПешечная структура и открытые линии."
    response = await admin_client.post(
        f"{API}/admin/rag/import",
        json={
            "filename": "plan.md",
            "contentBase64": base64.b64encode(markdown.encode()).decode(),
            "license": "MIT",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "draft"
    assert response.json()["license"] == "MIT"

    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(text="Chess tactic: hanging pieces and forks.")
    raw = bytes(pdf.output(dest="S"))  # type: ignore[call-overload]
    response = await admin_client.post(
        f"{API}/admin/rag/import",
        json={
            "filename": "tactics.pdf",
            "contentBase64": base64.b64encode(raw).decode(),
            "license": "internal",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "draft"
