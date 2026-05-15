"""add crawl mode fields to existing crawl_jobs

Revision ID: 20260515_0008
Revises: 20260514_0007
Create Date: 2026-05-15 18:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260515_0008"
down_revision: str | None = "20260514_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crawl_jobs",
        sa.Column("crawl_mode", sa.String(length=30), nullable=False, server_default="trusted_sources"),
    )
    op.add_column(
        "crawl_jobs",
        sa.Column("discovery_input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.alter_column("crawl_jobs", "crawl_mode", server_default=None)


def downgrade() -> None:
    op.drop_column("crawl_jobs", "discovery_input")
    op.drop_column("crawl_jobs", "crawl_mode")
