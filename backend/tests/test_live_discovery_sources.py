import os
from types import SimpleNamespace

import pytest

from app.services.discovery_sources import fetch_discovery_bundle_from_source


pytestmark = pytest.mark.live


def _require_live_web() -> None:
    if os.environ.get("RUN_LIVE_WEB_TESTS") != "true":
        pytest.skip("Set RUN_LIVE_WEB_TESTS=true to run live web-source tests.")


def test_live_unirank_vietnam_returns_real_rows_without_profile_url_as_website() -> None:
    _require_live_web()
    source = SimpleNamespace(
        id="src_live_unirank_vn",
        source_name="uniRank Vietnam Rankings",
        config={
            "source_type": "official_catalog_html",
            "url": "https://www.unirank.org/vn/ranking/",
            "parser_variant": "ranking_html",
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    assert len(bundle.rows) >= 20
    first = bundle.rows[0]
    assert first.normalized["name"]
    assert first.normalized["country"] == "Vietnam"
    assert first.normalized["source_url"].startswith("https://www.unirank.org/vn/uni/")
    assert first.normalized["reference_url"] == first.normalized["source_url"]
    assert first.normalized.get("website") in (None, "")


def test_live_wikipedia_vietnam_list_returns_real_evidence_links_without_official_website_guess() -> None:
    _require_live_web()
    source = SimpleNamespace(
        id="src_live_wikipedia_vn",
        source_name="Wikipedia Vietnam universities list",
        config={
            "source_type": "official_catalog_html",
            "url": "https://en.wikipedia.org/wiki/List_of_universities_in_Vietnam",
            "parser_variant": "wikipedia_list_html",
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    assert len(bundle.rows) >= 20
    first = bundle.rows[0]
    assert first.normalized["name"]
    assert first.normalized["country"] == "Vietnam"
    assert first.normalized["source_url"].startswith("https://en.wikipedia.org/wiki/")
    assert first.normalized["reference_url"] == first.normalized["source_url"]
    assert first.normalized.get("website") in (None, "")


def test_live_wikipedia_country_index_resolves_vietnam_list_without_hardcoded_country_url() -> None:
    _require_live_web()
    source = SimpleNamespace(
        id="src_live_wikipedia_country_index",
        source_name="Wikipedia universities by country index",
        config={
            "source_type": "official_catalog_html",
            "url": "https://en.wikipedia.org/wiki/Lists_of_universities_and_colleges_by_country",
            "parser_variant": "wikipedia_country_index_html",
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    assert len(bundle.rows) >= 20
    assert any("Vietnam" in row.normalized["name"] for row in bundle.rows)
    first = bundle.rows[0]
    assert first.normalized["country"] == "Vietnam"
    assert first.normalized["source_url"].startswith("https://en.wikipedia.org/wiki/")
    assert first.normalized.get("website") in (None, "")


def test_live_qs_world_rankings_returns_real_country_rows_without_official_website_guess() -> None:
    _require_live_web()
    source = SimpleNamespace(
        id="src_live_qs_rankings",
        source_name="QS World University Rankings",
        config={
            "source_type": "qs_rankings_json",
            "url": "https://www.topuniversities.com/world-university-rankings",
            "reference_url": "https://www.topuniversities.com/world-university-rankings",
            "data_url": "https://www.topuniversities.com/sites/default/files/qs-rankings-data/en/3740566.txt",
        },
    )

    bundle = fetch_discovery_bundle_from_source(source, country="Vietnam")

    assert len(bundle.rows) >= 1
    first = bundle.rows[0]
    assert first.normalized["name"]
    assert first.normalized["country"] == "Vietnam"
    assert first.normalized["source_url"].startswith("https://www.topuniversities.com/universities/")
    assert first.normalized["reference_url"] == "https://www.topuniversities.com/world-university-rankings"
    assert first.normalized.get("website") in (None, "")
