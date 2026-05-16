from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import requests

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/{qid}"
DEFAULT_USER_AGENT = "beyond2-university-crawler/1.0"


@dataclass(frozen=True)
class WikidataUniversityRow:
    wikidata_id: str
    name: str
    country: str
    country_label: str | None
    website: str | None
    founded: str | None
    coordinates: str | None
    description: str | None
    source_url: str
    snippet: str
    extraction_confidence: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "wikidata_id": self.wikidata_id,
            "name": self.name,
            "country": self.country,
            "country_label": self.country_label,
            "website": self.website,
            "founded": self.founded,
            "coordinates": self.coordinates,
            "description": self.description,
            "source_url": self.source_url,
            "snippet": self.snippet,
            "extraction_confidence": self.extraction_confidence,
        }


class WikidataImportError(RuntimeError):
    pass


class WikidataImporter:
    def __init__(self, *, contact_email: str | None = None, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.contact_email = contact_email
        self.session.headers.update(
            {
                "User-Agent": self._user_agent,
                "Accept": "application/json, application/sparql-results+json, text/json",
            }
        )
        if contact_email:
            self.session.headers.setdefault("From", contact_email)

    @property
    def _user_agent(self) -> str:
        if self.contact_email:
            return f"{DEFAULT_USER_AGENT} (contact: {self.contact_email})"
        return DEFAULT_USER_AGENT

    def fetch_universities_for_country(self, country_name: str, *, page_size: int = 100, max_pages: int = 10) -> list[dict[str, Any]]:
        try:
            rows = self._fetch_via_sparql(country_name, page_size=page_size, max_pages=max_pages)
            if rows:
                return rows
        except Exception:
            pass
        return self._fetch_via_rest(country_name)

    def _request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        response = self.session.request(method, url, timeout=60, **kwargs)
        response.raise_for_status()
        return response.json()

    def _fetch_via_sparql(self, country_name: str, *, page_size: int, max_pages: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for page_index in range(max_pages):
            offset = page_index * page_size
            query = f"""
            SELECT ?uni ?uniLabel ?uniDescription ?country ?countryLabel ?website ?founded ?coord WHERE {{
              ?uni wdt:P31/wdt:P279* wd:Q3918.
              ?uni wdt:P17 ?country.
              ?country rdfs:label \"{country_name}\"@en.
              OPTIONAL {{ ?uni wdt:P856 ?website. }}
              OPTIONAL {{ ?uni wdt:P571 ?founded. }}
              OPTIONAL {{ ?uni wdt:P625 ?coord. }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language \"vi,en\". }}
            }}
            LIMIT {page_size}
            OFFSET {offset}
            """.strip()
            payload = self._request_json(
                "POST",
                WIKIDATA_SPARQL_URL,
                data={"query": query, "format": "json"},
                headers={
                    "Accept": "application/sparql-results+json",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
            )
            bindings = (((payload or {}).get("results") or {}).get("bindings") or [])
            if not bindings:
                break
            for item in bindings:
                if not isinstance(item, dict):
                    continue
                uni_uri = ((item.get("uni") or {}).get("value"))
                if not uni_uri:
                    continue
                wikidata_id = uni_uri.rsplit("/", 1)[-1]
                if wikidata_id in seen_ids:
                    continue
                seen_ids.add(wikidata_id)
                name = self._binding_value(item, "uniLabel") or wikidata_id
                description = self._binding_value(item, "uniDescription")
                country_label = self._binding_value(item, "countryLabel") or country_name
                website = self._binding_value(item, "website")
                founded = self._binding_value(item, "founded")
                coordinates = self._binding_value(item, "coord")
                source_url = WIKIDATA_ENTITY_URL.format(qid=wikidata_id)
                snippet = self._make_snippet(name=name, description=description)
                rows.append(
                    WikidataUniversityRow(
                        wikidata_id=wikidata_id,
                        name=name,
                        country=country_name,
                        country_label=country_label,
                        website=website,
                        founded=founded,
                        coordinates=coordinates,
                        description=description,
                        source_url=source_url,
                        snippet=snippet,
                    ).as_dict()
                )
            if len(bindings) < page_size:
                break
        return rows

    def _fetch_via_rest(self, country_name: str) -> list[dict[str, Any]]:
        country_qid = self._lookup_country_qid(country_name)
        candidate_qids = self._collect_candidate_qids(country_name)
        entities = self._fetch_entities(candidate_qids)
        rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for qid, entity in entities.items():
            if not self._looks_like_university(entity):
                continue
            if country_qid and not self._entity_matches_country(entity, country_qid, country_name):
                continue
            if qid in seen_ids:
                continue
            seen_ids.add(qid)
            row = self._entity_to_row(qid, entity, country_name, country_qid)
            rows.append(row)
        return rows

    def _lookup_country_qid(self, country_name: str) -> str | None:
        payload = self._request_json(
            "GET",
            WIKIDATA_API_URL,
            params={
                "action": "wbsearchentities",
                "search": country_name,
                "language": "en",
                "type": "item",
                "limit": 10,
                "format": "json",
            },
        )
        results = payload.get("search") or []
        for item in results:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip().lower()
            title = str(item.get("display") or "").strip().lower()
            if label == country_name.strip().lower() or title == country_name.strip().lower():
                return str(item.get("id") or "") or None
        if results and isinstance(results[0], dict):
            return str(results[0].get("id") or "") or None
        return None

    def _collect_candidate_qids(self, country_name: str) -> list[str]:
        qids: list[str] = []
        seen: set[str] = set()
        search_terms = [f"{country_name} university", f"{country_name} college", "university", "college"]
        for search_term in search_terms:
            payload = self._request_json(
                "GET",
                WIKIDATA_API_URL,
                params={
                    "action": "wbsearchentities",
                    "search": search_term,
                    "language": "en",
                    "type": "item",
                    "limit": 50,
                    "format": "json",
                },
            )
            for item in payload.get("search") or []:
                if not isinstance(item, dict):
                    continue
                qid = str(item.get("id") or "").strip()
                if not qid or qid in seen:
                    continue
                seen.add(qid)
                qids.append(qid)
        return qids

    def _fetch_entities(self, qids: list[str]) -> dict[str, dict[str, Any]]:
        entities: dict[str, dict[str, Any]] = {}
        for batch in self._chunked(qids, 50):
            payload = self._request_json(
                "GET",
                WIKIDATA_API_URL,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(batch),
                    "props": "labels|descriptions|claims",
                    "languages": "en|vi",
                    "format": "json",
                },
            )
            batch_entities = payload.get("entities") or {}
            for qid, entity in batch_entities.items():
                if isinstance(entity, dict) and entity.get("missing") is None:
                    entities[qid] = entity
        return entities

    def _entity_to_row(self, qid: str, entity: dict[str, Any], country_name: str, country_qid: str | None) -> dict[str, Any]:
        label = self._best_label(entity)
        description = self._best_description(entity)
        country_label = country_name
        actual_country_qid = self._first_entity_claim_id(entity, "P17") or country_qid
        if actual_country_qid:
            country_label = self._label_for_qid(actual_country_qid) or country_name
        website = self._first_string_claim(entity, "P856")
        founded = self._first_time_claim(entity, "P571")
        coordinates = self._first_coordinate_claim(entity, "P625")
        snippet = self._make_snippet(name=label, description=description)
        source_url = WIKIDATA_ENTITY_URL.format(qid=qid)
        return WikidataUniversityRow(
            wikidata_id=qid,
            name=label,
            country=country_name,
            country_label=country_label,
            website=website,
            founded=founded,
            coordinates=coordinates,
            description=description,
            source_url=source_url,
            snippet=snippet,
        ).as_dict()

    def _looks_like_university(self, entity: dict[str, Any]) -> bool:
        instance_ids = set(self._claim_entity_ids(entity, "P31"))
        if "Q3918" in instance_ids:
            return True
        label = self._best_label(entity).lower()
        description = self._best_description(entity).lower()
        return "university" in label or "university" in description

    def _entity_matches_country(self, entity: dict[str, Any], country_qid: str, country_name: str) -> bool:
        country_ids = set(self._claim_entity_ids(entity, "P17"))
        if country_qid in country_ids:
            return True
        label = self._best_label(entity).lower()
        description = self._best_description(entity).lower()
        return country_name.strip().lower() in label or country_name.strip().lower() in description

    def _best_label(self, entity: dict[str, Any]) -> str:
        labels = entity.get("labels") or {}
        for language in ("vi", "en"):
            label = ((labels.get(language) or {}).get("value"))
            if label:
                return str(label)
        return str(entity.get("id") or "")

    def _best_description(self, entity: dict[str, Any]) -> str:
        descriptions = entity.get("descriptions") or {}
        for language in ("vi", "en"):
            description = ((descriptions.get(language) or {}).get("value"))
            if description:
                return str(description)
        return ""

    def _first_entity_claim_id(self, entity: dict[str, Any], prop: str) -> str | None:
        claim_ids = self._claim_entity_ids(entity, prop)
        return claim_ids[0] if claim_ids else None

    def _claim_entity_ids(self, entity: dict[str, Any], prop: str) -> list[str]:
        results: list[str] = []
        for claim in (entity.get("claims") or {}).get(prop) or []:
            mainsnak = (claim or {}).get("mainsnak") or {}
            datavalue = mainsnak.get("datavalue") or {}
            value = datavalue.get("value") or {}
            if isinstance(value, dict):
                entity_id = value.get("id")
                if entity_id:
                    results.append(str(entity_id))
        return results

    def _first_string_claim(self, entity: dict[str, Any], prop: str) -> str | None:
        for claim in (entity.get("claims") or {}).get(prop) or []:
            mainsnak = (claim or {}).get("mainsnak") or {}
            datavalue = mainsnak.get("datavalue") or {}
            value = datavalue.get("value")
            if value is not None:
                return str(value)
        return None

    def _first_time_claim(self, entity: dict[str, Any], prop: str) -> str | None:
        for claim in (entity.get("claims") or {}).get(prop) or []:
            mainsnak = (claim or {}).get("mainsnak") or {}
            datavalue = mainsnak.get("datavalue") or {}
            value = datavalue.get("value") or {}
            if isinstance(value, dict):
                time_value = value.get("time")
                if time_value:
                    return str(time_value)
        return None

    def _first_coordinate_claim(self, entity: dict[str, Any], prop: str) -> str | None:
        for claim in (entity.get("claims") or {}).get(prop) or []:
            mainsnak = (claim or {}).get("mainsnak") or {}
            datavalue = mainsnak.get("datavalue") or {}
            value = datavalue.get("value") or {}
            if isinstance(value, dict):
                lat = value.get("latitude")
                lon = value.get("longitude")
                if lat is not None and lon is not None:
                    return f"{lat},{lon}"
        return None

    def _label_for_qid(self, qid: str) -> str | None:
        payload = self._request_json(
            "GET",
            WIKIDATA_API_URL,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels",
                "languages": "en|vi",
                "format": "json",
            },
        )
        entity = ((payload.get("entities") or {}).get(qid)) or {}
        labels = entity.get("labels") or {}
        for language in ("vi", "en"):
            label = ((labels.get(language) or {}).get("value"))
            if label:
                return str(label)
        return None

    @staticmethod
    def _make_snippet(*, name: str, description: str | None) -> str:
        if description:
            return f"{name} — {description}"
        return name

    @staticmethod
    def _binding_value(item: dict[str, Any], key: str) -> str | None:
        value = ((item.get(key) or {}).get("value"))
        return str(value) if value is not None else None

    @staticmethod
    def _chunked(values: Iterable[str], size: int) -> Iterable[list[str]]:
        batch: list[str] = []
        for value in values:
            batch.append(value)
            if len(batch) >= size:
                yield batch
                batch = []
        if batch:
            yield batch


def fetch_wikidata_university_rows(country_name: str, *, contact_email: str | None = None, session: requests.Session | None = None) -> list[dict[str, Any]]:
    importer = WikidataImporter(contact_email=contact_email, session=session)
    return importer.fetch_universities_for_country(country_name)
