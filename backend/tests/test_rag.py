"""S-13: RAG — hash-эмбеддер, чанкинг, ingest+retrieval (admin)."""

import sqlalchemy as sa

from rag.embeddings import EMBED_DIM, hash_embedding
from rag.ingest import chunk_text
from tests.conftest import API, login, register_verified


def test_hash_embedding_deterministic_and_normalized():
    a = hash_embedding("циклы в python")
    b = hash_embedding("циклы в python")
    assert a == b
    assert len(a) == EMBED_DIM
    norm = sum(v * v for v in a) ** 0.5
    assert abs(norm - 1.0) < 0.01


def test_hash_embedding_different_texts_differ():
    assert hash_embedding("функции и return") != hash_embedding("вилки в шахматах")


def test_chunk_text_boundaries():
    text = "абзац один\n\nабзац два " + "слово " * 300
    chunks = chunk_text(text, chunk_chars=100, overlap=20)
    assert chunks
    assert all(len(c) <= 260 for c in chunks)  # 100 + запас слова
    assert len(chunks) >= 3


async def test_ingest_and_search_by_topic(admin_client):
    _ = admin_client  # seeds + admin bearer

    long_text = (
        "Функции в Python: def greet(name) возвращает строку через return. "
    ) * 10
    response = await admin_client.post(
        f"{API}/admin/rag/ingest",
        json={
            "titleRu": "Функции и return (тест)",
            "domain": "python",
            "kind": "explanation",
            "text": long_text,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["embedMode"] == "hash"  # dev без провайдера
    assert body["chunks"] >= 1

    # поиск по смыслу находит именно этот документ
    response = await admin_client.get(
        f"{API}/admin/rag/search", params={"q": "функции return python", "k": 3}
    )
    assert response.status_code == 200
    hits = response.json()["hits"]
    assert hits, "ожидаем хиты"
    assert "Функции и return" in hits[0]["titleRu"]

    # чистим тестовый инжест (он постоянный — не должен оставаться)
    from core.db import session_factory
    from rag.models import RagDocument

    async with session_factory() as session:
        doc = (
            await session.execute(
                sa.select(RagDocument).where(
                    RagDocument.title_ru == "Функции и return (тест)"
                )
            )
        ).scalar_one()
        await session.delete(doc)
        await session.commit()


async def test_search_requires_admin(make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    response = await client.get(
        f"{API}/admin/rag/search",
        params={"q": "тест"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 403
