"""add controls.embedding vector column

Revision ID: 002_controls_embedding
Revises: 001_compliance_tables
Create Date: 2026-06-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002_controls_embedding"
down_revision: Union[str, None] = "001_compliance_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "ALTER TABLE controls ADD COLUMN IF NOT EXISTS embedding vector(768)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE controls DROP COLUMN IF EXISTS embedding")
