from __future__ import annotations

import json
import os
import re


ISO_NUMERIC_COUNTRY_CODES = {
    "india": 356,
    "viet nam": 704,
    "vietnam": 704,
    "united states": 840,
    "usa": 840,
    "us": 840,
    "united kingdom": 826,
    "uk": 826,
}


def _match_key(value: object) -> str:
    text = str(value or "").strip().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _env_location_codes() -> dict[str, int]:
    raw = os.environ.get("BEYOND_LOCATION_CODES_JSON")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}

    codes: dict[str, int] = {}
    for country, code in payload.items():
        try:
            parsed = int(code)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            codes[_match_key(country)] = parsed
    return codes


def coerce_location_code(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"\d+", text):
            parsed = int(text)
            return parsed if parsed > 0 else None
    return None


def location_code_for_country(country: object) -> int | None:
    key = _match_key(country)
    if not key:
        return None
    env_codes = _env_location_codes()
    if key in env_codes:
        return env_codes[key]
    return ISO_NUMERIC_COUNTRY_CODES.get(key)
