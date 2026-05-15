from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

import httpx


_REPO_OWNER_PATTERN = r'<div class="[^"]*repoOwner[^"]*">(?P<short_name>.*?)</div>'
_REPO_NAME_PATTERN = r'<div class="[^"]*repoName[^"]*">(?P<name>.*?)</div>'
_DESC_PATTERN = r'<div class="[^"]*descCellExpanded[^"]*">(?P<description>.*?)</div>'
_CHIP_PATTERN = r'<span class="[^"]*chip[^"]*">(?P<value>.*?)</span>'
_URL_NAME_PATTERN = re.compile(
    r'\\"position\\":(?P<position>\d+),\\"url\\":\\"(?P<url>[^\\"]+)\\",\\"name\\":\\"(?P<name>(?:[^\\"]|\\.)*?)\\"'
)
_ROW_PATTERN = re.compile(
    r'<tr class="[^"]*clickableRow[^"]*"[^>]*>.*?'
    + _REPO_OWNER_PATTERN
    + r'.*?'
    + _REPO_NAME_PATTERN
    + r'.*?'
    + _DESC_PATTERN
    + r'(?P<tail>.*?)</tr>',
    re.S,
)


def _clean_html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def _decode_escaped_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace("\\/", "/")


def _source_urls_by_name(text: str) -> dict[str, str]:
    urls: dict[str, str] = {}
    for match in _URL_NAME_PATTERN.finditer(text):
        name = _decode_escaped_json_string(match.group("name")).strip()
        url = _decode_escaped_json_string(match.group("url")).strip()
        if name and url:
            urls.setdefault(name, url)
    return urls


def _rows_from_rendered_table(text: str, *, page_url: str, country: Any) -> list[dict[str, Any]]:
    urls_by_name = _source_urls_by_name(text)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, match in enumerate(_ROW_PATTERN.finditer(text), start=1):
        name = _clean_html_text(match.group("name"))
        if not name or name in seen:
            continue
        seen.add(name)
        tail = match.group("tail")
        chips = [_clean_html_text(value) for value in re.findall(_CHIP_PATTERN, tail, re.S)]
        source_url = urls_by_name.get(name)
        rows.append(
            {
                "name": name,
                "short_name": _clean_html_text(match.group("short_name")),
                "description": _clean_html_text(match.group("description")),
                "type": chips[0] if chips else None,
                "featured_major": chips[1] if len(chips) > 1 else None,
                "campuses": chips[2:] if len(chips) > 2 else [],
                "website": source_url,
                "source_url": source_url or page_url,
                "country": country,
                "position": index,
                "evidence": {
                    "source_page": page_url,
                    "parser": "rendered_table",
                },
            }
        )
    return rows


def load_escaped_jsonld_item_list(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Load rows from a source page with rendered table and escaped JSON-LD.

    The adapter is config-driven and source-agnostic. It is suitable for static
    Next/React pages that server-render a visible table and embed schema.org
    ListItem URLs for row provenance.
    """

    url = config.get("url") or config.get("source_url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("escaped_jsonld_item_list source requires url")

    response = httpx.get(
        url,
        headers=config.get("headers")
        or {"User-Agent": "Mozilla/5.0 BeyondDegreeBot/0.1 (+local development)"},
        timeout=float(config.get("timeout", 30)),
        follow_redirects=True,
    )
    response.raise_for_status()

    rows = _rows_from_rendered_table(response.text, page_url=str(response.url), country=config.get("country"))
    if rows:
        return rows

    rows = []
    seen: set[str] = set()
    for match in _URL_NAME_PATTERN.finditer(response.text):
        name = _decode_escaped_json_string(match.group("name")).strip()
        item_url = _decode_escaped_json_string(match.group("url")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        rows.append(
            {
                "name": name,
                "website": item_url,
                "source_url": item_url,
                "country": config.get("country"),
                "position": int(match.group("position")),
                "evidence": {
                    "source_page": str(response.url),
                    "schema": "schema.org/ListItem",
                },
            }
        )

    if not rows:
        raise ValueError("No rows found in escaped JSON-LD source")
    return rows
