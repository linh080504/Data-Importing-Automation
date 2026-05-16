from __future__ import annotations

import re


def _column_name(column: dict[str, object]) -> str:
    return str(column.get("name") or "").strip()


def _column_order(column: dict[str, object]) -> int:
    value = column.get("order", 0)
    return value if isinstance(value, int) else 0


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _slugify(value: object) -> str | None:
    if _is_empty(value):
        return None
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or None


def _rule_based_fill(
    column_name: str,
    mapped: dict[str, object | None],
    *,
    allow_rule_based_defaults: bool,
) -> object | None:
    lower = column_name.lower()

    if lower == "slug":
        return _slugify(mapped.get("name"))

    if allow_rule_based_defaults and lower in {"sponsored", "student_loan_available", "housing_availability", "immigration_support"}:
        return False

    return None


def map_clean_payload_to_template(
    clean_payload: dict[str, object],
    *,
    template_columns: list[dict[str, object]],
    defaults: dict[str, object] | None = None,
    allow_rule_based_defaults: bool = True,
) -> dict[str, object | None]:
    ordered_columns = sorted(template_columns, key=_column_order)
    default_values = defaults or {}

    mapped: dict[str, object | None] = {}
    for column in ordered_columns:
        column_name = _column_name(column)
        if not column_name:
            continue

        value = clean_payload.get(column_name)
        if _is_empty(value) and column_name in default_values:
            value = default_values[column_name]
        if _is_empty(value):
            value = _rule_based_fill(
                column_name,
                mapped,
                allow_rule_based_defaults=allow_rule_based_defaults,
            )

        mapped[column_name] = value

    return mapped
