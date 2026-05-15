"""initial schema

Revision ID: 20260509_0001
Revises:
Create Date: 2026-05-09 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260509_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("country", sa.String(length=50), nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("critical_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_data_sources_country"), "data_sources", ["country"], unique=False)

    op.create_table(
        "raw_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("unique_key", sa.String(length=100), nullable=False),
        sa.Column("record_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("crawled_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "unique_key", name="uq_raw_records_source_unique_key"),
    )
    op.create_index(op.f("ix_raw_records_source_id"), "raw_records", ["source_id"], unique=False)
    op.create_index("ix_raw_records_record_hash", "raw_records", ["record_hash"], unique=False)

    op.create_table(
        "clean_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("raw_record_id", sa.UUID(), nullable=True),
        sa.Column("unique_key", sa.String(length=100), nullable=False),
        sa.Column("clean_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unique_key", name="uq_clean_records_unique_key"),
    )
    op.create_index(op.f("ix_clean_records_raw_record_id"), "clean_records", ["raw_record_id"], unique=False)
    op.create_index("ix_clean_records_status", "clean_records", ["status"], unique=False)

    op.create_table(
        "review_actions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clean_record_id", sa.UUID(), nullable=True),
        sa.Column("reviewer_id", sa.String(length=100), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clean_record_id"], ["clean_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_actions_clean_record_id"), "review_actions", ["clean_record_id"], unique=False)

    op.create_table(
        "ai_extraction_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("raw_record_id", sa.UUID(), nullable=False),
        sa.Column("ai_1_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ai_2_validation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("overall_confidence", sa.Integer(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_extraction_logs_raw_record_id"), "ai_extraction_logs", ["raw_record_id"], unique=False)

    op.create_table(
        "import_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_system", sa.String(length=100), nullable=False),
        sa.Column("total_records", sa.Integer(), nullable=False),
        sa.Column("imported_records", sa.Integer(), nullable=False),
        sa.Column("failed_records", sa.Integer(), nullable=False),
        sa.Column("error_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("import_logs")
    op.drop_index(op.f("ix_ai_extraction_logs_raw_record_id"), table_name="ai_extraction_logs")
    op.drop_table("ai_extraction_logs")
    op.drop_index(op.f("ix_review_actions_clean_record_id"), table_name="review_actions")
    op.drop_table("review_actions")
    op.drop_index("ix_clean_records_status", table_name="clean_records")
    op.drop_index(op.f("ix_clean_records_raw_record_id"), table_name="clean_records")
    op.drop_table("clean_records")
    op.drop_index("ix_raw_records_record_hash", table_name="raw_records")
    op.drop_index(op.f("ix_raw_records_source_id"), table_name="raw_records")
    op.drop_table("raw_records")
    op.drop_index(op.f("ix_data_sources_country"), table_name="data_sources")
    op.drop_table("data_sources")
