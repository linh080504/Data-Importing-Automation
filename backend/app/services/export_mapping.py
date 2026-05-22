from __future__ import annotations

import re
from html import unescape

from app.services.country_location import coerce_location_code
from app.services.validator import is_plausible_phone_number, looks_like_tuition_financials


SAFE_FALSE_DEFAULT_FIELDS = {"sponsored"}


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


def _clean_html_text(value: object) -> str:
    text = re.sub(r"<sup[^>]*>.*?</sup>", " ", str(value or ""), flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = unescape(re.sub(r"<[^>]+>", " ", text))
    return " ".join(text.split())


def _clean_location(value: object) -> int | None:
    return coerce_location_code(value)


def _clean_template_value(column_name: str, value: object | None) -> object | None:
    if _is_empty(value):
        return None
    lower = column_name.lower()
    if lower == "location":
        return _clean_location(value)
    if lower == "financials" and not looks_like_tuition_financials(value):
        return None
    if "phone" in lower and not is_plausible_phone_number(value):
        return None
    if isinstance(value, str):
        if "<" in value and ">" in value:
            return _clean_html_text(value) or None
        return value
    return value


def _rule_based_fill(
    column_name: str,
    mapped: dict[str, object | None],
    *,
    allow_rule_based_defaults: bool,
) -> object | None:
    lower = column_name.lower()

    if lower == "slug":
        return _slugify(mapped.get("name"))

    if allow_rule_based_defaults and lower in SAFE_FALSE_DEFAULT_FIELDS:
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
        used_default = False
        if _is_empty(value) and column_name in default_values:
            value = default_values[column_name]
            used_default = True
        if _is_empty(value):
            value = _rule_based_fill(
                column_name,
                mapped,
                allow_rule_based_defaults=allow_rule_based_defaults,
            )

        clean_value = _clean_template_value(column_name, value)
        if _is_empty(clean_value) and not used_default and column_name in default_values:
            clean_value = _clean_template_value(column_name, default_values[column_name])

        mapped[column_name] = clean_value

    return mapped
