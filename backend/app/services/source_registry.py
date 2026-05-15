from __future__ import annotations

from copy import deepcopy
from typing import Any

_GLOBAL_SOURCE_COUNTRY = "*"

DEFAULT_TRUSTED_SOURCE_CATALOG: dict[str, list[dict[str, Any]]] = {
    "Vietnam": [
        {
            "name": "uniRank Vietnam Rankings",
            "source_type": "official_catalog_html",
            "country": "Vietnam",
            "config": {
                "url": "https://www.unirank.org/vn/ranking/",
                "role": "reference",
                "trust_level": "medium",
                "parser_variant": "ranking_html",
            },
            "supported_fields": ["name", "country", "website"],
        },
        {
            "name": "Wikidata Vietnam universities",
            "source_type": "wikidata_sparql",
            "country": "Vietnam",
            "config": {
                "url": "https://query.wikidata.org/sparql",
                "role": "reference",
                "trust_level": "high",
            },
            "supported_fields": ["name", "country", "website"],
        },
        {
            "name": "Wikipedia Vietnam universities list",
            "source_type": "official_catalog_html",
            "country": "Vietnam",
            "config": {
                "url": "https://vi.wikipedia.org/wiki/Danh_s%C3%A1ch_tr%C6%B0%E1%BB%9Dng_%C4%91%E1%BA%A1i_h%E1%BB%8Dc,_h%E1%BB%8Dc_vi%E1%BB%87n_v%C3%A0_cao_%C4%91%E1%BA%B3ng_t%E1%BA%A1i_Vi%E1%BB%87t_Nam",
                "role": "reference",
                "trust_level": "low",
                "parser_variant": "wikipedia_list_html",
            },
            "supported_fields": ["name", "country", "website"],
        },
    ],
    _GLOBAL_SOURCE_COUNTRY: [],
}


def _catalog_entries_for_country(country: str) -> list[dict[str, Any]]:
    requested_country = country.strip()
    return [
        *deepcopy(DEFAULT_TRUSTED_SOURCE_CATALOG.get(requested_country, [])),
        *deepcopy(DEFAULT_TRUSTED_SOURCE_CATALOG.get(_GLOBAL_SOURCE_COUNTRY, [])),
    ]


def recommended_sources_for_country(country: str) -> list[dict[str, Any]]:
    return _catalog_entries_for_country(country)


def resolve_trusted_source_plan(country: str) -> list[dict[str, Any]]:
    requested_country = country.strip()
    resolved_plan: list[dict[str, Any]] = []
    for index, entry in enumerate(_catalog_entries_for_country(requested_country), start=1):
        config = dict(entry.get("config") or {})
        resolved_plan.append(
            {
                "id": f"catalog:{requested_country}:{index}:{entry['name'].lower().replace(' ', '-')}",
                "name": entry["name"],
                "country": requested_country,
                "source_type": entry["source_type"],
                "supported_fields": list(entry.get("supported_fields") or []),
                "critical_fields": list(entry.get("critical_fields") or []),
                "config": {
                    **config,
                    "source_type": entry["source_type"],
                },
            }
        )
    return resolved_plan


def has_trusted_source_plan(country: str) -> bool:
    return len(resolve_trusted_source_plan(country)) > 0


def build_trusted_source_discovery_input(country: str) -> dict[str, Any]:
    source_plan = resolve_trusted_source_plan(country)
    return {
        "selected_source_ids": [],
        "source_plan": {
            "country": country.strip(),
            "sources": source_plan,
        },
    }


def source_names_from_discovery_input(discovery_input: dict[str, Any] | None) -> list[str]:
    payload = discovery_input or {}
    source_plan = payload.get("source_plan") or {}
    sources = source_plan.get("sources") if isinstance(source_plan, dict) else []
    if not isinstance(sources, list):
        return []
    return [str(source.get("name")) for source in sources if isinstance(source, dict) and source.get("name")]