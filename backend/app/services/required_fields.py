from __future__ import annotations

from typing import Any


DEFAULT_REQUIRED_FIELD_CANDIDATES = ("name",)


def template_column_names(template_columns: list[dict[str, Any]] | None) -> list[str]:
    if not template_columns:
        return []
    columns = [column for column in template_columns if isinstance(column, dict)]
    return [
        str(column.get("name")).strip()
        for column in sorted(columns, key=lambda item: item.get("order", 0) if isinstance(item.get("order", 0), int) else 0)
        if column.get("name") and str(column.get("name")).strip()
    ]


def required_fields_for_job(job: object, template_columns: list[dict[str, Any]] | None = None) -> list[str]:
    configured = getattr(job, "required_fields", None)
    if not isinstance(configured, list):
        discovery_input = getattr(job, "discovery_input", None)
        configured = discovery_input.get("required_fields") if isinstance(discovery_input, dict) else None

    template_fields = set(template_column_names(template_columns))
    if isinstance(configured, list):
        fields = [str(field).strip() for field in configured if str(field).strip()]
        return [field for field in fields if not template_fields or field in template_fields]

    return [field for field in DEFAULT_REQUIRED_FIELD_CANDIDATES if not template_fields or field in template_fields]
