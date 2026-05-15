"""add crawl jobs

Revision ID: 20260509_0004
Revises: 20260509_0003
Create Date: 2026-05-09 01:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260509_0004"
down_revision: str | None = "20260509_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crawl_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("country", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("crawl_mode", sa.String(length=30), nullable=False, server_default="trusted_sources"),
        sa.Column("discovery_input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("critical_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("clean_template_id", sa.UUID(), nullable=False),
        sa.Column("ai_assist", sa.Boolean(), nullable=False),
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clean_template_id"], ["clean_templates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_crawl_jobs_country"), "crawl_jobs", ["country"], unique=False)
    op.create_index(op.f("ix_crawl_jobs_status"), "crawl_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_crawl_jobs_status"), table_name="crawl_jobs")
    op.drop_index(op.f("ix_crawl_jobs_country"), table_name="crawl_jobs")
    op.drop_table("crawl_jobs")
