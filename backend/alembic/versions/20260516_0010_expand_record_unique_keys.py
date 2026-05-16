"""expand raw and clean record unique keys

Revision ID: 20260516_0010
Revises: 20260515_0009
Create Date: 2026-05-16 16:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260516_0010"
down_revision: str | None = "20260515_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "raw_records",
        "unique_key",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "clean_records",
        "unique_key",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    connection = op.get_bind()
    too_long = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1 FROM raw_records WHERE length(unique_key) > 100
                UNION ALL
                SELECT 1 FROM clean_records WHERE length(unique_key) > 100
            )
            """
        )
    ).scalar_one()
    if too_long:
        raise RuntimeError("Cannot downgrade unique_key columns to varchar(100) while long source keys exist.")

    op.alter_column(
        "clean_records",
        "unique_key",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
    op.alter_column(
        "raw_records",
        "unique_key",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
