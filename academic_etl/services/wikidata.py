"""Wikidata / Wikipedia institution discovery.

`WikidataSeedProvider` queries the Wikidata Query Service (SPARQL) for higher-
education institutions located in a given country and returns normalized seed
dicts (the same shape `discovery.run_discovery` consumes from hipolabs/csv).

The country is matched by its ISO 3166-1 alpha-2 code (Wikidata property P297),
so no hand-maintained country->QID map is needed. For each institution we
collect: label (name), official website (P856), country + ISO code, city /
admin region (P131), the English Wikipedia article URL, and the Wikidata QID.

Results are deduplicated (QID -> official domain -> normalized name + country +
city/region) before they are returned, so a single institution that appears in
several SPARQL rows (multiple cities/websites) collapses to one seed.
"""

import logging
from urllib.parse import urlparse

import requests

from .normalize import normalize_program_name, normalize_url, url_domain

logger = logging.getLogger(__name__)

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

# Higher-education institution (Q38723); P31/P279* catches universities,
# colleges, institutes of technology, etc. that subclass it.
SPARQL_TEMPLATE = """
SELECT ?item ?itemLabel ?website ?countryLabel ?code ?placeLabel ?article WHERE {
  ?country wdt:P297 "%(code)s" .
  ?item wdt:P31/wdt:P279* wd:Q38723 ;
        wdt:P17 ?country .
  OPTIONAL { ?item wdt:P856 ?website. }
  OPTIONAL { ?item wdt:P131 ?place. }
  OPTIONAL { ?country wdt:P297 ?code. }
  OPTIONAL {
    ?article schema:about ?item ;
             schema:isPartOf <https://en.wikipedia.org/> .
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT %(limit)d
"""

_BLOCKED_WEBSITE_HOSTS = ("wikipedia.org", "wikidata.org", "wikimedia.org")


def _qid_from_uri(uri: str) -> str:
    """`http://www.wikidata.org/entity/Q123` -> `Q123`."""
    return uri.rstrip("/").rsplit("/", 1)[-1] if uri else ""


def _is_blocked_website(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == b or host.endswith("." + b) for b in _BLOCKED_WEBSITE_HOSTS)


def _confidence(seed: dict) -> float:
    """Metadata-completeness score. Being in the higher-ed ontology is itself a
    strong signal, so the floor is high."""
    score = 0.6
    if seed.get("website"):
        score += 0.2
    if seed.get("wikipedia_url"):
        score += 0.1
    if seed.get("city") or seed.get("region"):
        score += 0.1
    return round(min(score, 1.0), 2)


def query_wikidata(code: str, limit: int, timeout: int, endpoint: str) -> list[dict]:
    """Run the SPARQL query and return raw binding dicts. Network boundary —
    patched in tests."""
    query = SPARQL_TEMPLATE % {"code": code, "limit": max(limit * 3, limit)}
    resp = requests.get(
        endpoint,
        params={"query": query, "format": "json"},
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": "BeyondDegreeBot/0.1 (academic data pipeline; contact: linhnguyenthuy0805@gmail.com)",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("results", {}).get("bindings", [])


def _binding_value(binding: dict, key: str) -> str:
    return (binding.get(key) or {}).get("value", "") or ""


class WikidataSeedProvider:
    """Discover higher-education institutions for a country from Wikidata."""

    source_name = "wikidata"

    def __init__(self, timeout: int = 60, endpoint: str = WIKIDATA_SPARQL_URL):
        self.timeout = timeout
        self.endpoint = endpoint

    def discover(self, country_name: str, country_code: str, limit: int = 200) -> list[dict]:
        code = (country_code or "").strip().upper()
        if not code:
            raise ValueError(
                "WikidataSeedProvider needs an ISO alpha-2 country code "
                f"(could not resolve one for {country_name!r})."
            )
        bindings = query_wikidata(code, limit, self.timeout, self.endpoint)
        logger.info("Wikidata: %s raw bindings for %s (%s)", len(bindings), country_name, code)
        seeds = self._bindings_to_seeds(bindings, country_name, code)
        deduped = self._dedup(seeds)
        return deduped[: limit or None]

    # ---- binding -> seed --------------------------------------------------

    def _bindings_to_seeds(self, bindings: list[dict], country_name: str, code: str) -> list[dict]:
        """Collapse SPARQL rows (one per item/city/website combo) into one seed
        per Wikidata QID, then build provider seed dicts."""
        by_qid: dict[str, dict] = {}
        for b in bindings:
            qid = _qid_from_uri(_binding_value(b, "item"))
            if not qid:
                continue
            name = _binding_value(b, "itemLabel").strip()
            if not name or name == qid:  # unlabeled entity — skip
                continue
            website = normalize_url(_binding_value(b, "website"))
            if website and _is_blocked_website(website):
                website = ""
            article = _binding_value(b, "article")
            place = _binding_value(b, "placeLabel").strip()

            acc = by_qid.setdefault(qid, {
                "name": name,
                "country": _binding_value(b, "countryLabel").strip() or country_name,
                "country_code": code,
                "city": "",
                "region": place,
                "website": "",
                "wikidata_qid": qid,
                "wikipedia_url": "",
                "source_name": self.source_name,
                "source_url": f"https://www.wikidata.org/wiki/{qid}",
                "_websites": [],
                "_places": [],
            })
            if website:
                acc["_websites"].append(website)
            if article:
                acc["wikipedia_url"] = acc["wikipedia_url"] or article
            if place and place not in acc["_places"]:
                acc["_places"].append(place)

        seeds = []
        for qid, acc in by_qid.items():
            acc["website"] = acc["_websites"][0] if acc["_websites"] else ""
            acc["region"] = acc["_places"][0] if acc["_places"] else ""
            acc["raw_json"] = {
                "wikidata_qid": qid,
                "name": acc["name"],
                "websites": acc["_websites"],
                "places": acc["_places"],
                "wikipedia_url": acc["wikipedia_url"],
                "country_code": acc["country_code"],
            }
            acc.pop("_websites", None)
            acc.pop("_places", None)
            acc["confidence"] = _confidence(acc)
            seeds.append(acc)
        return seeds

    # ---- dedup ------------------------------------------------------------

    @staticmethod
    def _dedup(seeds: list[dict]) -> list[dict]:
        """Drop duplicates by QID, then official domain, then
        normalized-name + country + city/region."""
        seen_qids: set[str] = set()
        seen_domains: set[str] = set()
        seen_name_keys: set[tuple] = set()
        out = []
        for seed in seeds:
            qid = seed.get("wikidata_qid", "")
            if qid and qid in seen_qids:
                continue
            domain = url_domain(seed.get("website", ""))
            if domain and domain in seen_domains:
                continue
            name_key = (
                normalize_program_name(seed.get("name", "")),
                (seed.get("country_code") or seed.get("country") or "").lower(),
                (seed.get("city") or seed.get("region") or "").lower(),
            )
            if name_key[0] and name_key in seen_name_keys:
                continue
            if qid:
                seen_qids.add(qid)
            if domain:
                seen_domains.add(domain)
            if name_key[0]:
                seen_name_keys.add(name_key)
            out.append(seed)
        return out
