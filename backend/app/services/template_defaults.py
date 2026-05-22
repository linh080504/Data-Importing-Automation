from __future__ import annotations

from app.services.country_location import coerce_location_code, location_code_for_country


def defaults_for_job(job: object) -> dict[str, object]:
    defaults: dict[str, object] = {}
    country = getattr(job, "country", None)
    if isinstance(country, str) and country.strip():
        defaults["country"] = country.strip()
        location_code = location_code_for_country(country)
        if location_code is not None:
            defaults["location"] = location_code

    discovery_input = getattr(job, "discovery_input", None)
    if isinstance(discovery_input, dict):
        explicit_code = (
            discovery_input.get("location_code")
            or discovery_input.get("location_id")
            or discovery_input.get("country_code")
        )
        location_code = coerce_location_code(explicit_code)
        if location_code is not None:
            defaults["location"] = location_code
    return defaults
