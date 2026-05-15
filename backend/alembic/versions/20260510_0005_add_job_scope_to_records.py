"""add job scope to raw and clean records

Revision ID: 20260510_0005
Revises: 20260509_0004
Create Date: 2026-05-10 10:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260510_0005"
down_revision: str | None = "20260509_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("raw_records", sa.Column("job_id", sa.UUID(), nullable=True))
    op.add_column("clean_records", sa.Column("job_id", sa.UUID(), nullable=True))

    connection = op.get_bind()
    raw_count = connection.execute(sa.text("SELECT COUNT(*) FROM raw_records")).scalar_one()
    clean_count = connection.execute(sa.text("SELECT COUNT(*) FROM clean_records")).scalar_one()
    if raw_count > 0 or clean_count > 0:
        raise RuntimeError("Cannot auto-backfill job_id for existing raw/clean records. Run a dedicated backfill before this migration.")

    op.alter_column("raw_records", "job_id", nullable=False)
    op.alter_column("clean_records", "job_id", nullable=False)

    op.drop_constraint("uq_raw_records_source_unique_key", "raw_records", type_="unique")
    op.drop_constraint("uq_clean_records_unique_key", "clean_records", type_="unique")

    op.create_foreign_key("fk_raw_records_job_id_crawl_jobs", "raw_records", "crawl_jobs", ["job_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_clean_records_job_id_crawl_jobs", "clean_records", "crawl_jobs", ["job_id"], ["id"], ondelete="CASCADE")
    op.create_index(op.f("ix_raw_records_job_id"), "raw_records", ["job_id"], unique=False)
    op.create_index(op.f("ix_clean_records_job_id"), "clean_records", ["job_id"], unique=False)
    op.create_unique_constraint("uq_raw_records_job_source_unique_key", "raw_records", ["job_id", "source_id", "unique_key"])
    op.create_unique_constraint("uq_clean_records_job_unique_key", "clean_records", ["job_id", "unique_key"])


def downgrade() -> None:
    op.drop_constraint("uq_clean_records_job_unique_key", "clean_records", type_="unique")
    op.drop_constraint("uq_raw_records_job_source_unique_key", "raw_records", type_="unique")
    op.drop_index(op.f("ix_clean_records_job_id"), table_name="clean_records")
    op.drop_index(op.f("ix_raw_records_job_id"), table_name="raw_records")
    op.drop_constraint("fk_clean_records_job_id_crawl_jobs", "clean_records", type_="foreignkey")
    op.drop_constraint("fk_raw_records_job_id_crawl_jobs", "raw_records", type_="foreignkey")
    op.create_unique_constraint("uq_clean_records_unique_key", "clean_records", ["unique_key"])
    op.create_unique_constraint("uq_raw_records_source_unique_key", "raw_records", ["source_id", "unique_key"])
    op.drop_column("clean_records", "job_id")
    op.drop_column("raw_records", "job_id")
