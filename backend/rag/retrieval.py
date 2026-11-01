"""Retrieval: топ-k чанков по косинусу (pgvector <=>)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from rag.embeddings import EmbeddingProvider

_TOP_K_SQL = text(
    """
    SELECT c.id, c.text, c.document_id, d.title_ru,
           1 - (c.embed <=> :query_vec) AS similarity
    FROM rag_chunks c
    JOIN rag_documents d ON d.id = c.document_id
    WHERE d.domain = ANY(:domains)
    ORDER BY c.embed <=> :query_vec
    LIMIT :k
    """
)


async def search(
    session: AsyncSession, query: str, *, k: int | None = None, domains: list[str] | None = None
) -> list[dict]:
    """Топ-k релевантных чанков (косинус; домены — фильтр, пусто = все)."""
    provider = EmbeddingProvider()
    [query_vec], _mode = await provider.embed([query])
    limit = k or settings.rag_top_k
    rows = (
        await session.execute(
            _TOP_K_SQL,
            {
                "query_vec": str(query_vec),
                "domains": domains or ["python", "chess", "general"],
                "k": limit,
            },
        )
    ).all()
    return [
        {
            "chunkId": str(row[0]),
            "documentId": str(row[2]),
            "titleRu": row[3],
            "text": row[1],
            "similarity": round(float(row[4]), 4),
        }
        for row in rows
    ]
