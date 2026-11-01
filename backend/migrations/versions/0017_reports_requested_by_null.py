"""S-41: reports_pdfs.requested_by → nullable (FK SET NULL).

Раньше FK был ON DELETE SET NULL, но колонка NOT NULL: удаление учителя,
сгенерировавшего PDF, падало. Приводим схему в соответствие с FK.

Revision ID: 0017_reports_requested_by_null
Revises: 0016_audit
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_reports_requested_by_null"
down_revision: str | None = "0016_audit"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "reports_pdfs",
        "requested_by",
        existing_type=sa.BigInteger(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "reports_pdfs",
        "requested_by",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
