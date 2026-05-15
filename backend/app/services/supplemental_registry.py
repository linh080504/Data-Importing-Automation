from __future__ import annotations

from copy import deepcopy
from typing import Any

_DEFAULT_SUPPLEMENTAL_COVERAGE_CATALOG: dict[str, list[dict[str, Any]]] = {
    "Vietnam": [
        {
            "name": "HEMIS public institution directory",
            "source_type": "json_api",
            "config": {
                "url": "https://hemis-cms.moet.gov.vn/gwdev/cosogiaoduc/v5/CO_SO_GIAO_DUC/getDefaultDropDown",
                "method": "POST",
                "body": {},
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
                    "Origin": "https://hemis-cms.moet.gov.vn",
                    "Referer": "https://hemis-cms.moet.gov.vn/",
                },
                "role": "supplemental",
                "trust_level": "low",
                "field_map": {
                    "name": ["teN_DON_VI", "teN_TIENG_ANH"],
                    "website": "website",
                    "country": "tinH_THANH_ID",
                },
                "unique_key_field": "id",
                "text_field": "teN_DON_VI",
            },
            "supported_fields": ["name", "country", "website"],
            "critical_fields": ["name", "website"],
        },
    ],
}


def resolve_supplemental_coverage_plan(country: str) -> list[dict[str, Any]]:
    requested_country = country.strip()
    entries = deepcopy(_DEFAULT_SUPPLEMENTAL_COVERAGE_CATALOG.get(requested_country, []))
    resolved_plan: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        config = dict(entry.get("config") or {})
        resolved_plan.append(
            {
                "id": f"supplemental:{requested_country}:{index}:{entry['name'].lower().replace(' ', '-')}",
                "name": entry["name"],
                "country": requested_country,
                "source_type": entry["source_type"],
                "supported_fields": list(entry.get("supported_fields") or []),
                "critical_fields": list(entry.get("critical_fields") or []),
                "config": {
                    **config,
                    "source_type": entry["source_type"],
                    "role": "supplemental",
                },
            }
        )
    return resolved_plan


def has_supplemental_coverage_plan(country: str) -> bool:
    return len(resolve_supplemental_coverage_plan(country)) > 0


def build_supplemental_discovery_input(country: str) -> dict[str, Any]:
    source_plan = resolve_supplemental_coverage_plan(country)
    return {
        "selected_source_ids": [],
        "supplemental_plan": {
            "country": country.strip(),
            "sources": source_plan,
        },
    }


def supplemental_source_names_from_discovery_input(discovery_input: dict[str, Any] | None) -> list[str]:
    payload = discovery_input or {}
    supplemental_plan = payload.get("supplemental_plan") or {}
    sources = supplemental_plan.get("sources") if isinstance(supplemental_plan, dict) else []
    if not isinstance(sources, list):
        return []
    return [str(source.get("name")) for source in sources if isinstance(source, dict) and source.get("name")]
