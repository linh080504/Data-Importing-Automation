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
            "supported_fields": ["name", "country", "source_url"],
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
            "supported_fields": ["name", "country", "website", "source_url"],
        },
    ],
    _GLOBAL_SOURCE_COUNTRY: [
        {
            "name": "Wikipedia universities by country index",
            "source_type": "official_catalog_html",
            "country": _GLOBAL_SOURCE_COUNTRY,
            "config": {
                "url": "https://en.wikipedia.org/wiki/Lists_of_universities_and_colleges_by_country",
                "role": "reference",
                "trust_level": "medium",
                "parser_variant": "wikipedia_country_index_html",
                "enrich_detail_pages": True,
                "enrich_official_site": True,
                "max_detail_pages": 240,
                "max_official_sites": 40,
                "detail_page_workers": 8,
                "official_site_workers": 5,
                "country_aliases": {
                    "USA": "United States",
                    "US": "United States",
                    "UK": "United Kingdom",
                },
            },
            "supported_fields": [
                "name",
                "country",
                "location",
                "description",
                "website",
                "source_url",
                "reference_url",
                "admissions_page_link",
                "admissions_contact",
                "admissions_phone",
                "financials",
                "campus_student_life",
                "number_of_students",
                "student_to_faculty_ratio",
                "international_student_ratio",
                "university_campuses",
                "global_rank",
            ],
        },
        {
            "name": "QS World University Rankings",
            "source_type": "qs_rankings_json",
            "country": _GLOBAL_SOURCE_COUNTRY,
            "config": {
                "url": "https://www.topuniversities.com/world-university-rankings",
                "reference_url": "https://www.topuniversities.com/world-university-rankings",
                "data_url": "https://www.topuniversities.com/sites/default/files/qs-rankings-data/en/3740566.txt",
                "role": "ranking_reference",
                "trust_level": "medium",
                "country_aliases": {
                    "USA": "United States",
                    "US": "United States",
                    "UK": "United Kingdom",
                },
            },
            "supported_fields": ["name", "country", "city", "global_rank", "rank_display", "qs_score", "source_url"],
        },
    ],
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
