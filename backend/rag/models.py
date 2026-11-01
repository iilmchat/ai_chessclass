"""ORM-модели RAG (Design §11.2); DDL — миграция 0009_rag."""

from datetime import datetime

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class RagDocument(Base):
    """Документ базы знаний (объяснения, эталоны, этюды)."""

    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    title_ru: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    domain: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # generated-колонка (миграция 0009) — исключена из INSERT/UPDATE
    tsv: Mapped[object] = mapped_column(
        TSVECTOR,
        sa.Computed("to_tsvector('russian', text)", persisted=True),
        nullable=True,
    )
    embed: Mapped[list] = mapped_column(Vector(768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RagChunk(Base):
    """Чанк документа с эмбеддингом (HNSW cosine-поиск)."""

    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embed: Mapped[list] = mapped_column(Vector(768), nullable=False)
