"""Retrieval: top-k гибрид vector + FTS (S-54)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from rag.embeddings import EmbeddingProvider

_TOP_K_SQL = text(
    """
    SELECT c.id, c.text, c.document_id, d.title_ru,
           1 - (c.embed <=> :query_vec) AS similarity,
           ts_rank_cd(d.tsv, plainto_tsquery('russian', :query)) AS lexical
    FROM rag_chunks c
    JOIN rag_documents d ON d.id = c.document_id
    WHERE d.domain = ANY(:domains)
      AND d.status = 'published'
    ORDER BY (
        0.7 * (1 - (c.embed <=> :query_vec))
        + 0.3 * COALESCE(
            ts_rank_cd(d.tsv, plainto_tsquery('russian', :query)), 0
        )
    ) DESC, c.embed <=> :query_vec
    LIMIT :k
    """
)

_VECTOR_SQL = text(
    """
    SELECT c.id, c.text, c.document_id, d.title_ru,
           1 - (c.embed <=> :query_vec) AS similarity,
           0.0 AS lexical
    FROM rag_chunks c
    JOIN rag_documents d ON d.id = c.document_id
    WHERE d.domain = ANY(:domains)
      AND d.status = 'published'
    ORDER BY c.embed <=> :query_vec
    LIMIT :k
    """
)


async def search(
    session: AsyncSession,
    query: str,
    *,
    k: int | None = None,
    domains: list[str] | None = None,
    mode: str = "hybrid",
) -> list[dict]:
    """Top-k поиск: гибрид vector + FTS (mode=vector — baseline)."""
    provider = EmbeddingProvider()
    [query_vec], _mode = await provider.embed([query])
    limit = k or settings.rag_top_k
    sql = _VECTOR_SQL if mode == "vector" else _TOP_K_SQL
    rows = (
        await session.execute(
            sql,
            {
                "query_vec": str(query_vec),
                "query": query,
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
            "lexical": round(float(row[5]), 4),
        }
        for row in rows
    ]
