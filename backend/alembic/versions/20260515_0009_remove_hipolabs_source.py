"""remove hipolabs data source

Revision ID: 20260515_0009
Revises: 20260515_0008
Create Date: 2026-05-15 19:10:00
"""

import uuid
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260515_0009"
down_revision: str | None = "20260515_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HIPOLABS_SOURCE_ID = uuid.uuid5(uuid.NAMESPACE_URL, "hipolabs-global")
_HIPOLABS_SOURCE = {
    "id": str(_HIPOLABS_SOURCE_ID),
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
}


def upgrade() -> None:
    op.execute(
        sa.text("DELETE FROM data_sources WHERE id = :id OR source_name = :source_name").bindparams(
            sa.bindparam("id", _HIPOLABS_SOURCE_ID, type_=postgresql.UUID()),
            sa.bindparam("source_name", _HIPOLABS_SOURCE["source_name"], type_=sa.String()),
        )
    )


def downgrade() -> None:
    sources_table = sa.table(
        "data_sources",
        sa.column("id", sa.UUID()),
        sa.column("country", sa.String()),
        sa.column("source_name", sa.String()),
        sa.column("supported_fields", postgresql.JSONB()),
        sa.column("critical_fields", postgresql.JSONB()),
        sa.column("config", postgresql.JSONB()),
    )

    op.execute(
        sources_table.insert().values(
            id=_HIPOLABS_SOURCE["id"],
            country=_HIPOLABS_SOURCE["country"],
            source_name=_HIPOLABS_SOURCE["source_name"],
            supported_fields=_HIPOLABS_SOURCE["supported_fields"],
            critical_fields=_HIPOLABS_SOURCE["critical_fields"],
            config=_HIPOLABS_SOURCE["config"],
        )
    )
