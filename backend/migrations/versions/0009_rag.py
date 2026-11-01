"""S-13: RAG — rag_documents + rag_chunks (vector 768, HNSW; Design §10.6).

tsv — полнотекстовый вектор для гибридного поиска (русский словарь);
embed — pgvector Vector(768), HNSW cosine (v0.1 ~100k векторов).

Revision ID: 0009_rag
Revises: 0008_chess_games
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0009_rag"
down_revision: str | None = "0008_chess_games"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

VECTOR_768 = Vector(768)


def upgrade() -> None:
    op.create_table(
        "rag_documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("title_ru", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('russian', text)", persisted=True),
        ),
        sa.Column("embed", VECTOR_768, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "domain IN ('python', 'chess', 'general')", name="domain_values"
        ),
        sa.CheckConstraint(
            "kind IN ('explanation', 'teacher_solution', 'chess_position', 'hint')",
            name="kind_values",
        ),
    )
    op.create_index(
        "ix_rag_documents_tsv", "rag_documents", ["tsv"], postgresql_using="gin"
    )

    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embed", VECTOR_768, nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_rag_chunks_embed_hnsw",
        "rag_chunks",
        ["embed"],
        postgresql_using="hnsw",
        postgresql_ops={"embed": "vector_cosine_ops"},
    )
    op.create_index("ix_rag_chunks_document", "rag_chunks", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_rag_chunks_document", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_embed_hnsw", table_name="rag_chunks")
    op.drop_table("rag_chunks")
    op.drop_index("ix_rag_documents_tsv", table_name="rag_documents")
    op.drop_table("rag_documents")
