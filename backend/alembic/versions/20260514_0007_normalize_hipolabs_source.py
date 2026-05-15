"""normalize hipolabs data source to global template

Revision ID: 20260514_0007
Revises: 20260513_0006
Create Date: 2026-05-14 00:00:00
"""

import uuid
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260514_0007"
down_revision: str = "20260513_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GLOBAL_SOURCE_ID = uuid.uuid5(uuid.NAMESPACE_URL, "hipolabs-global")
_LEGACY_SOURCE_IDS = [
    uuid.uuid5(uuid.NAMESPACE_URL, "hipolabs-vietnam"),
    uuid.uuid5(uuid.NAMESPACE_URL, "hipolabs-usa"),
]
_GLOBAL_SOURCE = {
    "id": _GLOBAL_SOURCE_ID,
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
        sa.text("DELETE FROM data_sources WHERE id = ANY(:ids)").bindparams(
            sa.bindparam("ids", _LEGACY_SOURCE_IDS, type_=postgresql.ARRAY(postgresql.UUID()))
        )
    )
    op.execute(
        sa.text("DELETE FROM data_sources WHERE id = :id").bindparams(
            sa.bindparam("id", _GLOBAL_SOURCE_ID, type_=postgresql.UUID())
        )
    )
    op.execute(
        sources_table.insert().values(
            id=_GLOBAL_SOURCE["id"],
            country=_GLOBAL_SOURCE["country"],
            source_name=_GLOBAL_SOURCE["source_name"],
            supported_fields=_GLOBAL_SOURCE["supported_fields"],
            critical_fields=_GLOBAL_SOURCE["critical_fields"],
            config=_GLOBAL_SOURCE["config"],
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM data_sources WHERE id = :id").bindparams(
            sa.bindparam("id", _GLOBAL_SOURCE_ID, type_=postgresql.UUID())
        )
    )
