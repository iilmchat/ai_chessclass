"""S-54: RAG-редактор — версии, статус, лицензия.

Revision ID: 0028_rag_editor
Revises: 0027_review
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_rag_editor"
down_revision: str | None = "0027_review"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rag_documents",
        sa.Column(
            "license", sa.String(length=64), nullable=False, server_default="unknown"
        ),
    )
    op.add_column(
        "rag_documents",
        sa.Column(
            "status", sa.String(length=12), nullable=False, server_default="published"
        ),
    )
    op.add_column(
        "rag_documents",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "rag_documents",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_check_constraint(
        "ck_rag_documents_rag_document_status_values",
        "rag_documents",
        "status IN ('draft', 'published', 'archived')",
    )
    op.create_index("ix_rag_documents_status", "rag_documents", ["status"])
    op.create_table(
        "rag_document_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title_ru", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("license", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["rag_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "document_id", "version", name="uq_rag_document_versions_version"
        ),
    )
    op.create_index(
        "ix_rag_document_versions_doc", "rag_document_versions", ["document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_rag_document_versions_doc", table_name="rag_document_versions")
    op.drop_table("rag_document_versions")
    op.drop_index("ix_rag_documents_status", table_name="rag_documents")
    op.drop_constraint(
        "ck_rag_documents_rag_document_status_values",
        "rag_documents",
        type_="check",
    )
    op.drop_column("rag_documents", "updated_at")
    op.drop_column("rag_documents", "version")
    op.drop_column("rag_documents", "status")
    op.drop_column("rag_documents", "license")
