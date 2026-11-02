"""Ingest: чанкинг текста → rag_documents + rag_chunks (embeddings)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from rag.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    """Чанкинг по абзацам с перекрытием (простой скользящий по символам)."""
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        # не рвать на середине слова: сдвигаем край до ближайшего разделителя
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary > start + chunk_chars // 2:
                end = boundary
            else:
                space = text.rfind(" ", start, end)
                if space > start + chunk_chars // 2:
                    end = space
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


async def ingest_document(
    session: AsyncSession,
    *,
    title_ru: str,
    source: str,
    domain: str,
    kind: str,
    text: str,
    license: str = "unknown",
    status: str = "published",
    created_by: int | None = None,
) -> dict:
    """Документ → чанки → embeddings → запись; повторный title = замена."""
    from rag.models import RagChunk, RagDocument, RagDocumentVersion

    existing = (
        await session.execute(select(RagDocument).where(RagDocument.title_ru == title_ru))
    ).scalar_one_or_none()
    if existing is not None:
        await session.delete(existing)  # чанки/версии каскадом
        await session.flush()

    provider = EmbeddingProvider()
    chunks = chunk_text(text, settings.rag_chunk_chars, settings.rag_chunk_overlap)
    vectors, mode = await provider.embed(chunks or [""])

    document = RagDocument(
        title_ru=title_ru,
        source=source,
        domain=domain,
        kind=kind,
        text=text,
        license=license,
        status=status,
        version=1,
        embed=vectors[0],
    )
    session.add(document)
    await session.flush()
    session.add(
        RagDocumentVersion(
            document_id=document.id,
            version=1,
            title_ru=title_ru,
            source=source,
            domain=domain,
            kind=kind,
            text=text,
            license=license,
            created_by=created_by,
        )
    )
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        session.add(
            RagChunk(document_id=document.id, idx=idx, text=chunk, embed=vector)
        )
    await session.flush()
    logger.info(
        "rag: инжест %r — %d чанков (%s)", title_ru, len(chunks), mode
    )
    return {"documentId": document.id, "chunks": len(chunks), "embedMode": mode}
