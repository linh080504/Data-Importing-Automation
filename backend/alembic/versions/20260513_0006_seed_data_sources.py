"""seed data sources with real university APIs

Revision ID: 20260513_0006
Revises: 20260510_0005
Create Date: 2026-05-13 00:00:00
"""

import uuid
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260513_0006"
down_revision: str = "20260510_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# Seed data: real public APIs that return university data per country.
# The backend's direct_run pipeline reads config.url → HTTP fetch → extract.
# ---------------------------------------------------------------------------
_SOURCES = [
    {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "hipolabs-global")),
        "country": "*",
        "source_name": "Hipolabs Universities API",
        "supported_fields": ["name", "website", "location", "domains"],
        "critical_fields": ["name", "website", "location"],
        "config": {
            "source_type": "json_api",
            "url_template": "http://universities.hipolabs.com/search?country={country_query}",
            "method": "GET",
            "role": "primary",
            "trust_level": "high",
            "note": "Public API — real university data resolved dynamically by selected country",
            "unique_key_field": "name",
            "country_aliases": {
                "USA": "United States",
                "UK": "United Kingdom",
            },
            "field_map": {
                "name": "name",
                "website": "web_pages",
                "location": ["state-province", "country"],
                "domains": "domains",
            },
            "text_field": None,
        },
    },
]


def upgrade() -> None:
    sources_table = sa.table(
        "data_sources",
        sa.column("id", sa.UUID()),
        sa.column("country", sa.String()),
        sa.column("source_name", sa.String()),
        sa.column("supported_fields", postgresql.JSONB()),
        sa.column("critical_fields", postgresql.JSONB()),
        sa.column("config", postgresql.JSONB()),
    )

    for source in _SOURCES:
        op.execute(
            sources_table.insert().values(
                id=source["id"],
                country=source["country"],
                source_name=source["source_name"],
                supported_fields=source["supported_fields"],
                critical_fields=source["critical_fields"],
                config=source["config"],
            )
        )


def downgrade() -> None:
    for source in _SOURCES:
        op.execute(
            sa.text("DELETE FROM data_sources WHERE id = :id").bindparams(id=source["id"])
        )
