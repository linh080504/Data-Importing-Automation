from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.schemas.discovery import DiscoveryRow, DiscoverySourceBundle


class DirectRunError(RuntimeError):
    pass


USER_AGENT = "beyond2-university-crawler/1.0"


def _request_json(method: str, url: str, **kwargs: Any) -> Any:
    headers = {"User-Agent": USER_AGENT, **(kwargs.pop("headers", {}) or {})}
    response = httpx.request(method, url, headers=headers, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def _request_text(method: str, url: str, **kwargs: Any) -> str:
    headers = {"User-Agent": USER_AGENT, **(kwargs.pop("headers", {}) or {})}
    response = httpx.request(method, url, headers=headers, timeout=30, **kwargs)
    response.raise_for_status()
    return response.text


def _source_rows(payload: Any, items_path: str | None) -> list[dict[str, Any]]:
    data = payload
    if items_path:
        for part in items_path.split("."):
            if not isinstance(data, dict) or part not in data:
                raise DirectRunError(f"Configured items_path '{items_path}' was not found in source response")
            data = data[part]

    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("items", "data", "results", "rows"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
        else:
            rows = [data]
    else:
        raise DirectRunError("Source response must be a JSON object or array")

    if not all(isinstance(row, dict) for row in rows):
        raise DirectRunError("Source rows must be JSON objects")
    return rows


def _pick_value(row: dict[str, Any], source_field: str | list[str] | None) -> Any:
    if source_field is None:
        return None
    if isinstance(source_field, str):
        return row.get(source_field)
    if isinstance(source_field, list):
        for field in source_field:
            if field in row:
                return row.get(field)
    return None


def _unique_key_for_row(row: dict[str, Any], *, unique_key_field: str | None, index: int) -> str:
    candidates = [unique_key_field, "unique_key", "id", "uuid", "code", "slug"]
    for candidate in candidates:
        if candidate and row.get(candidate) is not None:
            return str(row[candidate])
    return f"row-{index + 1}"


def _raw_text_for_row(source_row: dict[str, Any], text_field: str | None) -> str:
    if text_field and source_row.get(text_field) is not None:
        return str(source_row[text_field])
    return json.dumps(source_row, ensure_ascii=False)


def _normalize_country_alias(country: str, config: dict[str, Any]) -> str:
    aliases = config.get("country_aliases") or {}
    if not isinstance(aliases, dict):
        raise DirectRunError("country_aliases must be an object when provided")

    normalized_country = country.strip()
    alias = aliases.get(normalized_country)
    if alias is None:
        alias = aliases.get(normalized_country.lower())
    if alias is None:
        return normalized_country
    return str(alias).strip() or normalized_country


def _normalize_row(row: dict[str, Any], field_map: dict[str, Any] | None) -> dict[str, Any]:
    if not field_map:
        return dict(row)
    normalized = dict(row)
    for target_field, source_field in field_map.items():
        normalized[target_field] = _pick_value(row, source_field)
    return normalized


def _bundle_from_rows(*, source_id: str, source_name: str, rows: list[dict[str, Any]], config: dict[str, Any]) -> DiscoverySourceBundle:
    field_map = config.get("field_map") or {}
    text_field = config.get("text_field")
    unique_key_field = config.get("unique_key_field")
    normalized_rows: list[DiscoveryRow] = []
    for index, row in enumerate(rows):
        normalized = _normalize_row(row, field_map)
        normalized_rows.append(
            DiscoveryRow(
                source_id=source_id,
                source_name=source_name,
                unique_key=_unique_key_for_row(row, unique_key_field=unique_key_field, index=index),
                normalized=normalized,
                raw_payload=dict(row),
                raw_text=_raw_text_for_row(row, text_field),
            )
        )
    return DiscoverySourceBundle(source_id=source_id, source_name=source_name, rows=normalized_rows)


def _resolve_url(config: dict[str, Any], *, country: str | None) -> str:
    if config.get("url"):
        return str(config["url"])
    url_template = config.get("url_template")
    if not isinstance(url_template, str) or not url_template.strip():
        raise DirectRunError("Source config must include url or url_template")
    if not country:
        raise DirectRunError("Country is required for this source")
    country_name = _normalize_country_alias(country, config)
    country_query = quote_plus(country_name.replace(" ", "_"))
    return url_template.format(country=country_name, country_query=country_query, country_name=country_name)


def _extract_unirank_rows(html: str, *, country: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL):
        if "/vn/uni/" not in href:
            continue
        name = unescape(re.sub(r"<[^>]+>", " ", inner))
        name = " ".join(name.split())
        if len(name) < 4 or name in seen:
            continue
        seen.add(name)
        website = href if href.startswith("http") else f"https://www.unirank.org{href}"
        rows.append({"name": name, "country": country, "website": website, "source_href": website})
    return rows


def _extract_wikipedia_list_rows(html: str, *, country: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    main_content_match = re.search(r'<div[^>]+id="mw-content-text"[^>]*>(.*?)</div>', html, flags=re.IGNORECASE | re.DOTALL)
    main_content = main_content_match.group(1) if main_content_match else html
    for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', main_content, flags=re.IGNORECASE | re.DOTALL):
        if not href.startswith("/wiki/"):
            continue
        if any(prefix in href for prefix in ("/wiki/Special:", "/wiki/Help:", "/wiki/File:", "/wiki/Category:", "/wiki/Portal:")):
            continue
        if any(token in href for token in (":", "#", "Main_Page")):
            continue
        name = unescape(re.sub(r"<[^>]+>", " ", inner))
        name = " ".join(name.split())
        if len(name) < 6:
            continue
        lowered = name.lower()
        if any(term in lowered for term in ("edit", "citation", "vietnam", "list of", "ministry", "education", "contents")):
            continue
        if name in seen:
            continue
        seen.add(name)
        website = f"https://en.wikipedia.org{href}"
        rows.append({"name": name, "country": country, "website": website, "source_href": website})
    return rows


def fetch_discovery_bundle_from_source(source: object, *, country: str | None = None) -> DiscoverySourceBundle:
    config = dict(getattr(source, "config", None) or {})
    source_type = str(config.get("source_type", "json_api")).lower()
    source_id = str(getattr(source, "id", "source"))
    source_name = str(getattr(source, "source_name", source_id))

    if source_type in {"json_api", "official_catalog_json"}:
        url = _resolve_url(config, country=country)
        payload = _request_json(
            str(config.get("method", "GET")).upper(),
            url,
            params=config.get("params"),
            json=config.get("body"),
        )
        rows = _source_rows(payload, config.get("items_path"))
        return _bundle_from_rows(source_id=source_id, source_name=source_name, rows=rows, config=config)

    if source_type == "wikidata_sparql":
        query_country = country or "Vietnam"
        query = f"""
        SELECT ?uniLabel ?countryLabel ?website WHERE {{
          ?uni wdt:P31/wdt:P279* wd:Q3918.
          ?uni wdt:P17 ?country.
          ?country rdfs:label \"{query_country}\"@en.
          OPTIONAL {{ ?uni wdt:P856 ?website. }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language \"vi,en\". }}
        }}
        """.strip()
        payload = _request_json(
            "GET",
            _resolve_url(config, country=country),
            params={"format": "json", "query": query},
        )
        bindings = (((payload or {}).get("results") or {}).get("bindings") or [])
        rows = [
            {
                "name": ((item.get("uniLabel") or {}).get("value")),
                "country": ((item.get("countryLabel") or {}).get("value")) or query_country,
                "website": ((item.get("website") or {}).get("value")),
            }
            for item in bindings
            if isinstance(item, dict)
        ]
        config = {
            **config,
            "field_map": {"name": "name", "country": "country", "website": "website"},
            "unique_key_field": "website",
            "text_field": "name",
        }
        return _bundle_from_rows(source_id=source_id, source_name=source_name, rows=rows, config=config)

    if source_type in {"wikipedia_category", "official_catalog_html"}:
        url = _resolve_url(config, country=country)
        html = _request_text(str(config.get("method", "GET")).upper(), url)
        parser_variant = str(config.get("parser_variant", "")).lower()
        if parser_variant == "ranking_html":
            rows = _extract_unirank_rows(html, country=country)
            config = {
                **config,
                "field_map": {"name": "name", "country": "country", "website": "website"},
                "unique_key_field": "source_href",
                "text_field": "name",
            }
            return _bundle_from_rows(source_id=source_id, source_name=source_name, rows=rows, config=config)
        if parser_variant == "wikipedia_list_html":
            rows = _extract_wikipedia_list_rows(html, country=country)
            config = {
                **config,
                "field_map": {"name": "name", "country": "country", "website": "website"},
                "unique_key_field": "source_href",
                "text_field": "name",
            }
            return _bundle_from_rows(source_id=source_id, source_name=source_name, rows=rows, config=config)

        lines = [line.strip() for line in html.splitlines() if "title=" in line or "href=" in line]
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for line in lines:
            text = line.replace("<", " ").replace(">", " ")
            chunks = [chunk.strip() for chunk in text.split('"') if chunk.strip()]
            candidates = [chunk for chunk in chunks if len(chunk) > 3 and not chunk.startswith("http")]
            if not candidates:
                continue
            name = candidates[0]
            if name in seen:
                continue
            seen.add(name)
            rows.append({"name": name, "country": country, "website": None, "source_snippet": line[:500]})
        config = {
            **config,
            "field_map": {"name": "name", "country": "country", "website": "website"},
            "unique_key_field": "name",
            "text_field": "source_snippet",
        }
        return _bundle_from_rows(source_id=source_id, source_name=source_name, rows=rows, config=config)

    raise DirectRunError(f"Unsupported source_type '{source_type}'")
