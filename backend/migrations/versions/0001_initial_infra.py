"""S-01: инфраструктурная база БД — расширения (+ schema-заготовки).

Создаёт расширения PostgreSQL (Design §11.1):
- pgvector   — embeddings 768 (RAG, S-10+);
- pgcrypto   — крипто-утилиты (S-02);
- uuid-ossp  — uuid-генерация (S-02).

Витринные таблицы приходят отдельными миграциями доменов
(py_/chess_/bot_) начиная с S-02 — миграции доменов пишутся руками.

Revision ID: 0001_initial_infra
Revises:
Create Date: 2026-10-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial_infra"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: порядок: векторные зависимости последними (pgvector требует установку бинаря)
EXTENSIONS: tuple[str, ...] = ("uuid-ossp", "pgcrypto", "vector")


def upgrade() -> None:
    for ext in EXTENSIONS:
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')


def downgrade() -> None:
    for ext in reversed(EXTENSIONS):
        op.execute(f'DROP EXTENSION IF EXISTS "{ext}"')
