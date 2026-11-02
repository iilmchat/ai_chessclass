"""S-44: voice_audio — кэш озвучки ElevenLabs.

Revision ID: 0020_voice
Revises: 0019_studies
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_voice"
down_revision: str | None = "0019_studies"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_audio",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("voice_id", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("chars", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="elevenlabs"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("text_hash", name="uq_voice_audio_text_hash"),
    )


def downgrade() -> None:
    op.drop_table("voice_audio")
