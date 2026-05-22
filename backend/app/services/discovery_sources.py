from __future__ import annotations

import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from typing import Any
from urllib.parse import quote_plus, unquote, urljoin, urlparse

import httpx

from app.schemas.discovery import DiscoveryRow, DiscoverySourceBundle
from app.services.country_location import coerce_location_code
from app.services.validator import is_plausible_phone_number, looks_like_tuition_financials
from app.services.wikidata_importer import fetch_wikidata_university_rows


class DirectRunError(RuntimeError):
    pass


USER_AGENT = "beyond2-university-crawler/1.0"
WIKIPEDIA_DOMAINS = ("wikipedia.org", "wikimedia.org", "wikidata.org")
NON_SCHOOL_EXTERNAL_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "google.com",
    "wikipedia.org",
    "wikidata.org",
    "wikimedia.org",
    "unirank.org",
)

INFOBOX_FIELD_ALIASES = {
    "location": ("location", "address", "city"),
    "website": ("website",),
    "number_of_students": ("students", "student", "total students"),
    "student_to_faculty_ratio": ("student to faculty ratio", "student-faculty ratio", "student–faculty ratio"),
    "international_student_ratio": ("international students", "international student"),
    "university_campuses": ("campus", "campuses"),
    "global_rank": ("ranking", "rankings"),
}

OFFICIAL_LINK_PATTERNS = {
    "admissions_page_link": (
        "admission",
        "admissions",
        "apply",
        "enrollment",
        "tuyen-sinh",
        "tuyensinh",
        "tuyen sinh",
        "tuyển sinh",
        "xet-tuyen",
        "xet tuyen",
    ),
    "financials_source_url": (
        "tuition",
        "tuition fee",
        "tuition fees",
        "fee",
        "fees",
        "fee structure",
        "fees-and-funding",
        "fees and funding",
        "cost",
        "hoc-phi",
        "hoc phi",
        "học phí",
    ),
    "campus_student_life_source_url": (
        "student-life",
        "student life",
        "campus life",
        "life",
        "students",
        "sinh-vien",
        "sinh vien",
        "sinh viên",
    ),
    "housing_source_url": (
        "housing",
        "dorm",
        "dormitory",
        "accommodation",
        "ký túc",
        "ky-tuc",
        "ky tuc",
    ),
    "international_source_url": (
        "international",
        "visa",
        "immigration",
        "global",
        "quoc-te",
        "quoc te",
        "quốc tế",
    ),
}

ARTICLE_DETAIL_FIELDS = {
    "description",
    "global_rank",
    "international_student_ratio",
    "location",
    "number_of_students",
    "student_to_faculty_ratio",
    "university_campuses",
    "website",
}

OFFICIAL_SITE_ENRICHMENT_FIELDS = {
    "admissions_contact",
    "admissions_page_link",
    "admissions_phone",
    "campus_student_life",
    "contact_person",
    "financials",
    "housing_availability",
    "immigration_support",
    "student_loan_available",
}


def _request_json(method: str, url: str, **kwargs: Any) -> Any:
    headers = {"User-Agent": USER_AGENT, **(kwargs.pop("headers", {}) or {})}
    try:
        response = httpx.request(method, url, headers=headers, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()
    except Exception:
        # Retry with a more browser-like User-Agent and Accept header (helps for SPARQL endpoints)
        try:
            contact = os.environ.get("WIKIDATA_CONTACT_EMAIL")
            fallback_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36",
                "Accept": "application/sparql-results+json, application/json, text/json",
            }
            if contact:
                fallback_headers["From"] = contact
                fallback_headers["User-Agent"] = f"beyond2-university-crawler/1.0 (contact: {contact})"
            response = httpx.request(method, url, headers={**fallback_headers, **headers}, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception:
            raise


def _request_text(method: str, url: str, **kwargs: Any) -> str:
    headers = {"User-Agent": USER_AGENT, **(kwargs.pop("headers", {}) or {})}
    response = httpx.request(method, url, headers=headers, timeout=15, **kwargs)
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


def _match_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("đ", "d")
    text = text.replace("viet nam", "vietnam")
    text = text.replace("ha noi", "hanoi")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


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


def _wikipedia_rest_html_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "wikipedia.org" not in parsed.netloc.lower() or not parsed.path.startswith("/wiki/"):
        return None
    title = parsed.path.removeprefix("/wiki/")
    if not title:
        return None
    return f"{parsed.scheme or 'https'}://{parsed.netloc}/api/rest_v1/page/html/{title}"


def _request_public_html(method: str, url: str, *, parser_variant: str, referer: str | None = None) -> str:
    try:
        return _request_text(method, url)
    except Exception as exc:
        candidate_urls: list[str] = []
        if parser_variant in {"wikipedia_list_html", "wikipedia_country_index_html", "wikipedia_article_html"}:
            rest_url = _wikipedia_rest_html_url(url)
            if rest_url:
                candidate_urls.append(rest_url)
        candidate_urls.append(url)

        fallback_error: Exception = exc
        for candidate_url in candidate_urls:
            try:
                if "/api/rest_v1/page/html/" in candidate_url:
                    contact = os.environ.get("WIKIDATA_CONTACT_EMAIL") or "local-dev@example.invalid"
                    headers = {
                        "User-Agent": f"{USER_AGENT} (contact: {contact})",
                        "Accept": "text/html",
                        "Referer": referer or url,
                    }
                else:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Referer": referer or url,
                    }
                response = httpx.request(method, candidate_url, headers=headers, timeout=15, follow_redirects=True)
                response.raise_for_status()
                return response.text
            except Exception as retry_exc:
                fallback_error = retry_exc
        raise fallback_error


def _request_official_html(url: str, *, referer: str | None = None) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    response = httpx.request("GET", url, headers=headers, timeout=6, follow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower() and response.text.strip().startswith("{"):
        raise DirectRunError("Official site response was not HTML")
    return response.text


def _wikipedia_base_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "https://en.wikipedia.org"


def _wikipedia_article_url(href: str, *, base_url: str) -> str | None:
    if href.startswith("./"):
        return f"{base_url}/wiki/{href[2:]}"
    if href.startswith("/wiki/"):
        return f"{base_url}{href}"
    if re.match(r"https?://[a-z0-9.-]*wikipedia.org/wiki/", href, flags=re.IGNORECASE):
        return href
    return None


def _is_external_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    netloc = parsed.netloc.lower()
    return not any(domain in netloc for domain in WIKIPEDIA_DOMAINS)


def _is_school_website_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    netloc = parsed.netloc.lower()
    return not any(domain in netloc for domain in NON_SCHOOL_EXTERNAL_DOMAINS)


def _external_url_from_href(href: str, *, base_url: str) -> str | None:
    if href.startswith("//"):
        href = f"https:{href}"
    url = urljoin(base_url, href)
    return url if _is_external_url(url) else None


def _first_external_link(fragment: str, *, base_url: str) -> str | None:
    for href in re.findall(r'<a[^>]+href="([^"]+)"', fragment, flags=re.IGNORECASE | re.DOTALL):
        url = _external_url_from_href(unescape(href), base_url=base_url)
        if url:
            return url
    return None


def _wikipedia_content_html(html: str) -> str:
    parser_match = re.search(
        r'<div[^>]+class="[^"]*\bmw-parser-output\b[^"]*"[^>]*>(.*?)(?:<div[^>]+class="[^"]*\bprintfooter\b|<div[^>]+id="catlinks"|</body>)',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if parser_match:
        return parser_match.group(1)
    content_match = re.search(
        r'<div[^>]+id="mw-content-text"[^>]*>(.*?)(?:<div[^>]+id="catlinks"|</body>)',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return content_match.group(1) if content_match else html


def _is_wikipedia_non_school_url(source_url: str) -> bool:
    if any(token in source_url for token in ("/wiki/Special:", "/wiki/Help:", "/wiki/File:", "/wiki/Category:", "/wiki/Portal:", "/wiki/Talk:")):
        return True
    page_ref = source_url.rsplit("/wiki/", 1)[-1]
    if any(token in page_ref for token in (":", "#", "Main_Page")):
        return True
    page_title = unquote(page_ref).replace("_", " ").lower()
    return page_title.startswith(("list of universities", "lists of universities", "list of colleges", "lists of colleges"))


def _clean_school_name(value: object) -> str:
    text = _clean_html_text(value)
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -;:,")


def _clean_location_value(value: object) -> int | None:
    return coerce_location_code(value)


def _stable_fragment(value: object) -> str:
    key = _match_key(value)
    return "-".join(key.split())[:120] or "row"


def _add_wikipedia_row(
    rows_by_key: dict[str, dict[str, Any]],
    *,
    name: str,
    country: str | None,
    source_url: str,
    reference_url: str,
    location: str | None = None,
    snippet: str | None = None,
) -> None:
    clean_name = _clean_school_name(name)
    if len(clean_name) < 3:
        return
    lowered = clean_name.lower()
    if any(term in lowered for term in ("edit", "citation", "contents", "references", "list of")):
        return
    if lowered in {"university", "university system", "national key university"}:
        return
    if not _looks_like_university_entry(clean_name, source_url):
        return

    key = _match_key(clean_name)
    existing = rows_by_key.get(key)
    if existing is not None:
        if existing.get("source_url") == existing.get("reference_url") and source_url != reference_url:
            existing["source_url"] = source_url
            existing["source_href"] = source_url
        if location and not existing.get("location"):
            clean_location = _clean_location_value(location)
            if clean_location:
                existing["location"] = clean_location
        if snippet and not existing.get("snippet"):
            existing["snippet"] = snippet
        return

    rows_by_key[key] = {
        "name": clean_name,
        "country": country,
        "source_url": source_url,
        "reference_url": reference_url,
        "source_href": source_url,
    }
    if location:
        clean_location = _clean_location_value(location)
        if clean_location:
            rows_by_key[key]["location"] = clean_location
    if snippet:
        rows_by_key[key]["snippet"] = _clean_school_name(snippet)


def _extract_wikipedia_country_list_url(html: str, *, country: str, index_url: str, config: dict[str, Any]) -> str:
    country_name = _normalize_country_alias(country, config)
    country_key = _match_key(country_name)
    if not country_key:
        raise DirectRunError("Country is required for Wikipedia country-index source")

    base_url = _wikipedia_base_url(index_url)
    main_content = _wikipedia_content_html(html)

    for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', main_content, flags=re.IGNORECASE | re.DOTALL):
        label = " ".join(unescape(re.sub(r"<[^>]+>", " ", inner)).split())
        if _match_key(label) != country_key:
            continue
        source_url = _wikipedia_article_url(href, base_url=base_url)
        if source_url:
            return source_url

    raise DirectRunError(f"Wikipedia country index does not include a university-list link for {country_name}")


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
        source_url = href if href.startswith("http") else f"https://www.unirank.org{href}"
        rows.append({"name": name, "country": country, "source_url": source_url, "reference_url": source_url, "source_href": source_url})
    return rows


def _extract_meta_description(html: str) -> str | None:
    match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if not match:
        return None
    text = _clean_html_text(match.group(1))
    return text if len(text) >= 40 else None


def _first_school_external_link(html: str, *, base_url: str) -> str | None:
    labeled_candidates: list[str] = []
    fallback_candidates: list[str] = []
    for href, label_html in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL):
        url = urljoin(base_url, unescape(href))
        if not _is_school_website_url(url):
            continue
        label = _clean_html_text(label_html).lower()
        if "website" in label or "official" in label:
            labeled_candidates.append(url)
        else:
            fallback_candidates.append(url)
    return (labeled_candidates or fallback_candidates or [None])[0]


def _extract_unirank_detail_details(html: str, *, detail_url: str, country: str | None) -> dict[str, Any]:
    details: dict[str, Any] = {
        "source_url": detail_url,
        "reference_url": detail_url,
        "source_href": detail_url,
        "country": country,
    }

    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        details["name"] = _clean_school_name(title_match.group(1))

    description = _extract_meta_description(html) or _extract_first_article_paragraph(html)
    if description:
        details["description"] = description

    website = _first_school_external_link(html, base_url=detail_url)
    if website:
        details["website"] = website

    text = _clean_html_text(html)
    location_match = re.search(r"(?:address|location|city)\s*[:\-]\s*([^|]{4,180})", text, flags=re.IGNORECASE)
    if location_match:
        location = _clean_location_value(location_match.group(1))
        if location:
            details["location"] = location

    snippet_parts = [str(details.get("name") or ""), str(details.get("description") or ""), str(details.get("location") or "")]
    details["snippet"] = " | ".join(part for part in snippet_parts if part)
    return details


def _extract_wikipedia_list_rows(html: str, *, country: str | None, list_url: str | None = None) -> list[dict[str, Any]]:
    rows_by_key: dict[str, dict[str, Any]] = {}
    main_content = _wikipedia_content_html(html)
    domain_match = re.search(r"https?://[a-z0-9.-]*wikipedia.org", html, flags=re.IGNORECASE)
    base_candidate = list_url or (domain_match.group(0) if domain_match else "https://en.wikipedia.org")
    wiki_base = _wikipedia_base_url(base_candidate)
    reference_url = list_url or wiki_base

    for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', main_content, flags=re.IGNORECASE | re.DOTALL):
        source_url = _wikipedia_article_url(href, base_url=wiki_base)
        if not source_url or _is_wikipedia_non_school_url(source_url):
            continue
        name = _clean_school_name(inner)
        _add_wikipedia_row(
            rows_by_key,
            name=name,
            country=country,
            source_url=source_url,
            reference_url=reference_url,
        )

    for row in _extract_wikipedia_table_rows(main_content, country=country, base_url=wiki_base, reference_url=reference_url):
        _add_wikipedia_row(
            rows_by_key,
            name=str(row.get("name") or ""),
            country=country,
            source_url=str(row.get("source_url") or reference_url),
            reference_url=reference_url,
            location=str(row.get("location") or "") or None,
            snippet=str(row.get("snippet") or "") or None,
        )

    return list(rows_by_key.values())


def _extract_wikipedia_table_rows(
    html: str,
    *,
    country: str | None,
    base_url: str,
    reference_url: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table_html in re.findall(r"<table\b[^>]*>(.*?)</table>", html, flags=re.IGNORECASE | re.DOTALL):
        headers: list[str] = []
        for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL):
            cells = re.findall(r"<(t[dh])\b[^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL)
            if not cells:
                continue
            cell_values = [_clean_school_name(cell_html) for _tag, cell_html in cells]
            if all(tag.lower() == "th" for tag, _cell_html in cells) or _looks_like_header_row(cell_values):
                headers = [_match_key(value) for value in cell_values]
                continue
            row = _wikipedia_table_row_from_cells(cells, headers=headers, country=country, base_url=base_url, reference_url=reference_url)
            if row:
                rows.append(row)
    return rows


def _looks_like_header_row(values: list[str]) -> bool:
    header_text = " ".join(_match_key(value) for value in values)
    return bool(header_text) and any(token in header_text for token in ("english name", "vietnamese name", "abbreviation", "location", "institution", "school"))


def _wikipedia_cell_article(cell_html: str, *, base_url: str) -> tuple[str, str | None]:
    best_name = ""
    best_url: str | None = None
    for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', cell_html, flags=re.IGNORECASE | re.DOTALL):
        source_url = _wikipedia_article_url(unescape(href), base_url=base_url)
        if not source_url or _is_wikipedia_non_school_url(source_url):
            continue
        name = _clean_school_name(inner)
        if _looks_like_university_entry(name, source_url):
            return name, source_url
        if not best_name:
            best_name = name
            best_url = source_url
    return best_name, best_url


def _cell_candidate_score(name: str, source_url: str | None, header: str) -> int:
    if not name or not _looks_like_university_entry(name, source_url or ""):
        return -1
    header_key = _match_key(header)
    if any(token in header_key for token in ("location", "city", "province", "abbreviation", "vietnamese")):
        return -1
    score = 10
    if source_url:
        score += 20
    if any(token in header_key for token in ("english name", "institution", "university system", "member", "school", "name")):
        score += 20
    name_key = _match_key(name)
    if any(term in name_key for term in ("university", "academy", "institute", "college", "polytechnic", "conservatory")):
        score += 10
    if name.lower().startswith(("faculty of ", "department of ")):
        score -= 25
    return score


def _wikipedia_table_row_from_cells(
    cells: list[tuple[str, str]],
    *,
    headers: list[str],
    country: str | None,
    base_url: str,
    reference_url: str,
) -> dict[str, Any] | None:
    best: tuple[int, str, str | None] | None = None
    location: str | None = None
    snippets: list[str] = []

    for index, (_tag, cell_html) in enumerate(cells):
        header = headers[index] if index < len(headers) else ""
        text = _clean_school_name(cell_html)
        if not text:
            continue
        if any(token in header for token in ("location", "city", "province")):
            location = _clean_location_value(text)
            continue
        if re.fullmatch(r"\d+\.?", text):
            continue
        snippets.append(text)
        anchor_name, source_url = _wikipedia_cell_article(cell_html, base_url=base_url)
        candidate_name = anchor_name or text
        score = _cell_candidate_score(candidate_name, source_url, header)
        if best is None or score > best[0]:
            best = (score, candidate_name, source_url)

    if best is None or best[0] < 0:
        return None

    name = best[1]
    source_url = best[2] or f"{reference_url}#{_stable_fragment(name)}"
    return {
        "name": name,
        "country": country,
        "location": location,
        "source_url": source_url,
        "reference_url": reference_url,
        "source_href": source_url,
        "snippet": " | ".join(snippets[:5]),
    }


def _looks_like_university_entry(name: str, source_url: str) -> bool:
    haystack = _match_key(f"{name} {source_url}".replace("_", " "))
    school_terms = (
        "university",
        "universities",
        "college",
        "institute",
        "academy",
        "school",
        "conservatory",
        "polytechnic",
        "hoc vien",
        "dai hoc",
    )
    return any(term in haystack for term in school_terms)


def _clean_html_text(value: object) -> str:
    text = re.sub(r"<sup[^>]*>.*?</sup>", " ", str(value or ""), flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = unescape(re.sub(r"<[^>]+>", " ", text))
    return " ".join(text.split())


def _extract_first_article_paragraph(html: str) -> str | None:
    main_content_match = re.search(r'<div[^>]+id="mw-content-text"[^>]*>(.*?)</div>', html, flags=re.IGNORECASE | re.DOTALL)
    main_content = main_content_match.group(1) if main_content_match else html
    for paragraph in re.findall(r"<p[^>]*>(.*?)</p>", main_content, flags=re.IGNORECASE | re.DOTALL):
        text = _clean_html_text(paragraph)
        if len(text) >= 80:
            return text
    return None


def _extract_infobox_rows(html: str) -> dict[str, dict[str, str | None]]:
    infobox_match = re.search(r'<table[^>]+class="[^"]*\binfobox\b[^"]*"[^>]*>(.*?)</table>', html, flags=re.IGNORECASE | re.DOTALL)
    if not infobox_match:
        return {}
    rows: dict[str, dict[str, str | None]] = {}
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", infobox_match.group(1), flags=re.IGNORECASE | re.DOTALL):
        header_match = re.search(r"<th[^>]*>(.*?)</th>", row_html, flags=re.IGNORECASE | re.DOTALL)
        data_match = re.search(r"<td[^>]*>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if not header_match or not data_match:
            continue
        label = _match_key(_clean_html_text(header_match.group(1)))
        value_html = data_match.group(1)
        value = _clean_html_text(value_html)
        if not label or not value:
            continue
        rows[label] = {"value": value, "external_url": None}
        external_url = _first_external_link(value_html, base_url="https://en.wikipedia.org")
        if external_url:
            rows[label]["external_url"] = external_url
    return rows


def _infobox_value(infobox: dict[str, dict[str, str | None]], aliases: tuple[str, ...]) -> tuple[str | None, str | None]:
    alias_keys = {_match_key(alias) for alias in aliases}
    for label, payload in infobox.items():
        if label in alias_keys or any(alias in label for alias in alias_keys):
            return payload.get("value"), payload.get("external_url")
    return None, None


def _extract_wikipedia_article_details(html: str, *, article_url: str, country: str | None) -> dict[str, Any]:
    base_url = _wikipedia_base_url(article_url)
    details: dict[str, Any] = {
        "source_url": article_url,
        "reference_url": article_url,
        "source_href": article_url,
        "country": country,
    }

    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        details["name"] = _clean_html_text(title_match.group(1))

    description = _extract_first_article_paragraph(html)
    if description:
        details["description"] = description

    infobox = _extract_infobox_rows(html)
    for field_name, aliases in INFOBOX_FIELD_ALIASES.items():
        value, external_url = _infobox_value(infobox, aliases)
        if field_name == "website":
            if external_url:
                details["website"] = external_url
            elif value and re.match(r"https?://", value):
                details["website"] = value
            continue
        if field_name == "location":
            clean_location = _clean_location_value(value)
            if clean_location:
                details["location"] = clean_location
            continue
        if value:
            details[field_name] = value

    if not details.get("website"):
        for href, label_html in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL):
            label = _clean_html_text(label_html).lower()
            if "official website" not in label and "website" != label:
                continue
            external_url = _external_url_from_href(unescape(href), base_url=base_url)
            if external_url:
                details["website"] = external_url
                break

    snippet_parts = [str(details.get("name") or ""), str(details.get("description") or ""), str(details.get("location") or "")]
    details["snippet"] = " | ".join(part for part in snippet_parts if part)
    details["wikipedia_article_url"] = article_url
    return details


def _extract_links_by_patterns(html: str, *, page_url: str) -> dict[str, str]:
    matches: dict[str, str] = {}
    base_url = page_url
    for href, label_html in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL):
        url = urljoin(base_url, unescape(href))
        if not _is_external_url(url):
            continue
        haystack = f"{_clean_html_text(label_html)} {url}".lower()
        haystack_key = _match_key(haystack)
        for field_name, patterns in OFFICIAL_LINK_PATTERNS.items():
            if field_name in matches:
                continue
            if any(pattern.lower() in haystack or _match_key(pattern) in haystack_key for pattern in patterns):
                matches[field_name] = url
    return matches


def _first_email(html: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", html)
    return match.group(0) if match else None


PHONE_CONTEXT_PATTERNS = (
    "phone",
    "telephone",
    "tel",
    "hotline",
    "contact",
    "admission",
    "admissions",
    "tuyen sinh",
    "tuyensinh",
    "dien thoai",
    "điện thoại",
)

FINANCIAL_CONTEXT_PATTERNS = (
    "tuition",
    "tuition fee",
    "tuition fees",
    "fee",
    "fees",
    "fee structure",
    "cost of attendance",
    "hoc phi",
    "học phí",
    "le phi",
    "lệ phí",
)


def _normalize_phone_candidate(value: object) -> str | None:
    text = unescape(str(value or ""))
    text = re.sub(r"^\s*tel:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:ext|extension|may le|máy lẻ)\s*[:.]?\s*\d+\b", "", text, flags=re.IGNORECASE)
    match = re.search(r"\+?\d[\d\s().-]{6,}\d", text)
    if not match:
        return None
    candidate = " ".join(match.group(0).split())
    return candidate if is_plausible_phone_number(candidate) else None


def _first_phone(html: str) -> str | None:
    for tel_href in re.findall(r'href=["\']\s*tel:([^"\']+)["\']', html, flags=re.IGNORECASE):
        candidate = _normalize_phone_candidate(tel_href)
        if candidate:
            return candidate

    text = _clean_html_text(html)
    for match in re.finditer(r"\+?\d[\d\s().-]{6,}\d", text):
        start = max(match.start() - 90, 0)
        end = min(match.end() + 90, len(text))
        context = text[start:end].lower()
        context_key = _match_key(context)
        if not any(pattern in context or _match_key(pattern) in context_key for pattern in PHONE_CONTEXT_PATTERNS):
            continue
        candidate = _normalize_phone_candidate(match.group(0))
        if candidate:
            return candidate
    return None


def _financial_context_matches(text: str) -> bool:
    lower = text.lower()
    match_key = _match_key(text)
    return any(pattern in lower or _match_key(pattern) in match_key for pattern in FINANCIAL_CONTEXT_PATTERNS)


def _text_segments(html: str) -> list[str]:
    segments: list[str] = []
    for tag in ("tr", "p", "li"):
        for chunk in re.findall(fr"<{tag}[^>]*>(.*?)</{tag}>", html, flags=re.IGNORECASE | re.DOTALL):
            text = _clean_html_text(chunk)
            if text:
                segments.append(text)
    whole_text = _clean_html_text(html)
    for sentence in re.split(r"(?<=[.!?])\s+|\s+[|•]\s+", whole_text):
        sentence = sentence.strip()
        if sentence:
            segments.append(sentence)
    return segments


def _trim_financial_segment(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= 260:
        return compact
    lower = compact.lower()
    indexes = [lower.find(pattern) for pattern in FINANCIAL_CONTEXT_PATTERNS if lower.find(pattern) >= 0]
    index = min(indexes) if indexes else 0
    start = max(index - 80, 0)
    end = min(index + 220, len(compact))
    return compact[start:end].strip(" ;,.-")


def _extract_financials_value(html: str) -> str | None:
    for segment in _text_segments(html):
        if not _financial_context_matches(segment):
            continue
        candidate = _trim_financial_segment(segment)
        if looks_like_tuition_financials(candidate):
            return candidate
    return None


def _snippet_around(html: str, patterns: tuple[str, ...]) -> str | None:
    text = _clean_html_text(html)
    lower = text.lower()
    normalized = _match_key(text)
    for pattern in patterns:
        index = lower.find(pattern.lower())
        if index < 0:
            normalized_pattern = _match_key(pattern)
            normalized_index = normalized.find(normalized_pattern)
            if normalized_index < 0:
                continue
            words = text.split()
            start_word = max(normalized[:normalized_index].count(" ") - 25, 0)
            return " ".join(words[start_word:start_word + 80]).strip()
        start = max(index - 180, 0)
        end = min(index + 420, len(text))
        return text[start:end].strip()
    return None


def _enrich_with_official_site(row: dict[str, Any], *, referer: str | None = None) -> None:
    website = row.get("website")
    if not isinstance(website, str) or not website.strip():
        return
    try:
        html = _request_official_html(website.strip(), referer=referer)
    except Exception:
        return

    related_links = {key: value for key, value in _extract_links_by_patterns(html, page_url=website).items() if value}
    row.update(related_links)

    page_html_by_field: dict[str, str] = {"homepage": html}
    for link_field, link_url in list(related_links.items())[:6]:
        if not isinstance(link_url, str) or not link_url.strip():
            continue
        try:
            page_html_by_field[link_field] = _request_official_html(link_url.strip(), referer=website.strip())
        except Exception:
            continue

    admissions_html = page_html_by_field.get("admissions_page_link", html)
    financials_html = page_html_by_field.get("financials_source_url", html)
    campus_life_html = page_html_by_field.get("campus_student_life_source_url", html)
    housing_html = page_html_by_field.get("housing_source_url", html)
    international_html = page_html_by_field.get("international_source_url", html)

    email = _first_email(admissions_html) or _first_email(html)
    if email and not row.get("admissions_contact"):
        row["admissions_contact"] = email
    phone = _first_phone(admissions_html) or _first_phone(html)
    if phone and not row.get("admissions_phone"):
        row["admissions_phone"] = phone
    financials = _extract_financials_value(financials_html)
    if financials and not row.get("financials"):
        row["financials"] = financials
    student_life = _snippet_around(campus_life_html, OFFICIAL_LINK_PATTERNS["campus_student_life_source_url"])
    if student_life and not row.get("campus_student_life"):
        row["campus_student_life"] = student_life
    housing = _snippet_around(housing_html, OFFICIAL_LINK_PATTERNS["housing_source_url"])
    if housing and not row.get("housing_availability"):
        row["housing_availability"] = True
    international = _snippet_around(international_html, OFFICIAL_LINK_PATTERNS["international_source_url"])
    if international and not row.get("immigration_support"):
        row["immigration_support"] = True


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _normalized_focus_fields(focus_fields: list[str] | tuple[str, ...] | None) -> set[str]:
    return {str(field).strip() for field in (focus_fields or []) if str(field).strip()}


def _should_enrich_wikipedia_details(config: dict[str, Any], focus_fields: set[str]) -> bool:
    if not config.get("enrich_detail_pages"):
        return False
    if not focus_fields:
        return True
    return bool(focus_fields & (ARTICLE_DETAIL_FIELDS | OFFICIAL_SITE_ENRICHMENT_FIELDS))


def _should_enrich_official_sites(config: dict[str, Any], focus_fields: set[str]) -> bool:
    if not config.get("enrich_official_site"):
        return False
    if not focus_fields:
        return True
    return bool(focus_fields & OFFICIAL_SITE_ENRICHMENT_FIELDS)


def _enrich_wikipedia_article_row(
    index: int,
    row: dict[str, Any],
    *,
    country: str | None,
    referer: str | None,
) -> tuple[int, dict[str, Any]]:
    enriched = dict(row)
    article_url = row.get("source_url")
    if not isinstance(article_url, str) or not article_url.strip():
        return index, enriched
    article_url = article_url.strip()
    if _is_wikipedia_non_school_url(article_url):
        return index, enriched
    try:
        html = _request_public_html("GET", article_url, parser_variant="wikipedia_article_html", referer=referer)
        details = _extract_wikipedia_article_details(html, article_url=article_url, country=country)
        enriched = {**details, **{key: value for key, value in enriched.items() if value not in (None, "", [], {})}}
        if details.get("website") and not row.get("website"):
            enriched["website"] = details["website"]
        if details.get("description") and not row.get("description"):
            enriched["description"] = details["description"]
    except Exception:
        pass
    return index, enriched


def _enrich_official_site_row(index: int, row: dict[str, Any], *, referer: str | None) -> tuple[int, dict[str, Any]]:
    enriched = dict(row)
    _enrich_with_official_site(enriched, referer=referer)
    return index, enriched


def _enrich_unirank_detail_row(
    index: int,
    row: dict[str, Any],
    *,
    country: str | None,
    referer: str | None,
) -> tuple[int, dict[str, Any]]:
    enriched = dict(row)
    detail_url = row.get("source_url")
    if not isinstance(detail_url, str) or not detail_url.strip():
        return index, enriched
    try:
        html = _request_public_html("GET", detail_url.strip(), parser_variant="ranking_detail_html", referer=referer)
        details = _extract_unirank_detail_details(html, detail_url=detail_url.strip(), country=country)
        enriched = {**details, **{key: value for key, value in enriched.items() if value not in (None, "", [], {})}}
        if details.get("website") and not row.get("website"):
            enriched["website"] = details["website"]
        if details.get("description") and not row.get("description"):
            enriched["description"] = details["description"]
        if details.get("location") and not row.get("location"):
            enriched["location"] = details["location"]
    except Exception:
        pass
    return index, enriched


def _enrich_unirank_rows(
    rows: list[dict[str, Any]],
    *,
    country: str | None,
    config: dict[str, Any],
    referer: str | None,
    focus_fields: set[str],
) -> list[dict[str, Any]]:
    if not config.get("enrich_detail_pages") and not config.get("enrich_official_site"):
        return rows

    max_detail_pages = min(_positive_int(config.get("max_detail_pages"), len(rows)), len(rows))
    detail_workers = min(_positive_int(config.get("detail_page_workers"), 6), max_detail_pages or 1)
    enriched_rows: list[dict[str, Any]] = [dict(row) for row in rows]

    if max_detail_pages > 0 and config.get("enrich_detail_pages"):
        detail_candidates = [(index, rows[index]) for index in range(max_detail_pages)]
        if detail_workers <= 1 or len(detail_candidates) <= 1:
            for index, row in detail_candidates:
                result_index, enriched = _enrich_unirank_detail_row(index, row, country=country, referer=referer)
                enriched_rows[result_index] = enriched
        else:
            with ThreadPoolExecutor(max_workers=detail_workers) as executor:
                futures = [
                    executor.submit(_enrich_unirank_detail_row, index, row, country=country, referer=referer)
                    for index, row in detail_candidates
                ]
                for future in as_completed(futures):
                    result_index, enriched = future.result()
                    enriched_rows[result_index] = enriched

    if not _should_enrich_official_sites(config, focus_fields):
        return enriched_rows

    max_official_sites = _positive_int(config.get("max_official_sites"), 0)
    if max_official_sites <= 0:
        return enriched_rows

    official_candidates = [
        (index, row)
        for index, row in enumerate(enriched_rows)
        if isinstance(row.get("website"), str) and str(row.get("website")).strip()
    ][:max_official_sites]
    official_workers = min(_positive_int(config.get("official_site_workers"), 4), len(official_candidates) or 1)
    if official_workers <= 1 or len(official_candidates) <= 1:
        for index, row in official_candidates:
            result_index, enriched = _enrich_official_site_row(index, row, referer=str(row.get("source_url") or referer or ""))
            enriched_rows[result_index] = enriched
        return enriched_rows

    with ThreadPoolExecutor(max_workers=official_workers) as executor:
        futures = [
            executor.submit(_enrich_official_site_row, index, row, referer=str(row.get("source_url") or referer or ""))
            for index, row in official_candidates
        ]
        for future in as_completed(futures):
            result_index, enriched = future.result()
            enriched_rows[result_index] = enriched
    return enriched_rows


def _enrich_wikipedia_rows(
    rows: list[dict[str, Any]],
    *,
    country: str | None,
    config: dict[str, Any],
    referer: str | None,
    focus_fields: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    normalized_focus_fields = _normalized_focus_fields(focus_fields)
    if not _should_enrich_wikipedia_details(config, normalized_focus_fields):
        return rows

    max_detail_pages = min(_positive_int(config.get("max_detail_pages"), len(rows)), len(rows))
    detail_workers = min(_positive_int(config.get("detail_page_workers"), 6), max_detail_pages or 1)
    enriched_rows: list[dict[str, Any]] = [dict(row) for row in rows]

    if max_detail_pages > 0:
        detail_candidates = [(index, rows[index]) for index in range(max_detail_pages)]
        if detail_workers <= 1 or len(detail_candidates) <= 1:
            for index, row in detail_candidates:
                result_index, enriched = _enrich_wikipedia_article_row(index, row, country=country, referer=referer)
                enriched_rows[result_index] = enriched
        else:
            with ThreadPoolExecutor(max_workers=detail_workers) as executor:
                futures = [
                    executor.submit(_enrich_wikipedia_article_row, index, row, country=country, referer=referer)
                    for index, row in detail_candidates
                ]
                for future in as_completed(futures):
                    result_index, enriched = future.result()
                    enriched_rows[result_index] = enriched

    if not _should_enrich_official_sites(config, normalized_focus_fields):
        return enriched_rows

    max_official_sites = _positive_int(config.get("max_official_sites"), 0)
    if max_official_sites <= 0:
        return enriched_rows

    official_candidates = [
        (index, row)
        for index, row in enumerate(enriched_rows)
        if isinstance(row.get("website"), str) and str(row.get("website")).strip()
    ][:max_official_sites]
    official_workers = min(_positive_int(config.get("official_site_workers"), 4), len(official_candidates) or 1)
    if official_workers <= 1 or len(official_candidates) <= 1:
        for index, row in official_candidates:
            result_index, enriched = _enrich_official_site_row(
                index,
                row,
                referer=str(row.get("wikipedia_article_url") or referer or ""),
            )
            enriched_rows[result_index] = enriched
        return enriched_rows

    with ThreadPoolExecutor(max_workers=official_workers) as executor:
        futures = [
            executor.submit(
                _enrich_official_site_row,
                index,
                row,
                referer=str(row.get("wikipedia_article_url") or referer or ""),
            )
            for index, row in official_candidates
        ]
        for future in as_completed(futures):
            result_index, enriched = future.result()
            enriched_rows[result_index] = enriched
    return enriched_rows


def _first_anchor(value: object, *, base_url: str) -> tuple[str, str | None]:
    html = str(value or "")
    match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return _clean_html_text(html), None
    href = match.group(1)
    label = _clean_html_text(match.group(2))
    return label, urljoin(base_url, href)


def _extract_qs_ranking_rows(payload: Any, *, country: str | None, config: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise DirectRunError("QS ranking payload must contain a data list")

    country_name = _normalize_country_alias(country or "", config) if country else ""
    country_key = _match_key(country_name)
    base_url = str(config.get("profile_base_url") or "https://www.topuniversities.com")
    reference_url = str(config.get("reference_url") or config.get("url") or "https://www.topuniversities.com/world-university-rankings")

    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row_country = str(item.get("country") or "").strip()
        if country_key and _match_key(row_country) != country_key:
            continue
        name, profile_url = _first_anchor(item.get("title"), base_url=base_url)
        if not name:
            continue
        source_url = profile_url or reference_url
        rows.append(
            {
                "name": name,
                "country": row_country or country,
                "city": item.get("city"),
                "region": item.get("region"),
                "rank_display": item.get("rank_display"),
                "global_rank": item.get("rank_display"),
                "qs_score": item.get("score"),
                "source_url": source_url,
                "reference_url": reference_url,
                "source_href": source_url,
                "snippet": f"{name} | QS rank {item.get('rank_display') or 'unranked'} | {row_country}",
            }
        )
    return rows


def fetch_discovery_bundle_from_source(
    source: object,
    *,
    country: str | None = None,
    focus_fields: list[str] | tuple[str, ...] | None = None,
) -> DiscoverySourceBundle:
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
        rows = fetch_wikidata_university_rows(
            query_country,
            contact_email=os.environ.get("WIKIDATA_CONTACT_EMAIL"),
        )
        config = {
            **config,
            "field_map": {
                "name": "name",
                "country": "country",
                "country_label": "country_label",
                "website": "website",
                "founded": "founded",
                "coordinates": "coordinates",
                "description": "description",
                "source_url": "source_url",
                "snippet": "snippet",
                "wikidata_id": "wikidata_id",
                "extraction_confidence": "extraction_confidence",
            },
            "unique_key_field": "wikidata_id",
            "text_field": "snippet",
        }
        return _bundle_from_rows(source_id=source_id, source_name=source_name, rows=rows, config=config)

    if source_type == "qs_rankings_json":
        data_url = str(config.get("data_url") or _resolve_url(config, country=country))
        payload = _request_json(str(config.get("method", "GET")).upper(), data_url)
        rows = _extract_qs_ranking_rows(payload, country=country, config=config)
        config = {
            **config,
            "field_map": {
                "name": "name",
                "country": "country",
                "city": "city",
                "region": "region",
                "rank_display": "rank_display",
                "global_rank": "global_rank",
                "qs_score": "qs_score",
                "source_url": "source_url",
                "reference_url": "reference_url",
                "snippet": "snippet",
            },
            "unique_key_field": "source_href",
            "text_field": "snippet",
        }
        return _bundle_from_rows(source_id=source_id, source_name=source_name, rows=rows, config=config)

    if source_type in {"wikipedia_category", "official_catalog_html"}:
        url = _resolve_url(config, country=country)
        parser_variant = str(config.get("parser_variant", "")).lower()
        html = _request_public_html(str(config.get("method", "GET")).upper(), url, parser_variant=parser_variant)
        if parser_variant == "wikipedia_country_index_html":
            if not country:
                raise DirectRunError("Country is required for Wikipedia country-index source")
            country_list_url = _extract_wikipedia_country_list_url(html, country=country, index_url=url, config=config)
            html = _request_public_html(str(config.get("method", "GET")).upper(), country_list_url, parser_variant="wikipedia_list_html", referer=url)
            rows = _extract_wikipedia_list_rows(html, country=country, list_url=country_list_url)
            rows = _enrich_wikipedia_rows(rows, country=country, config=config, referer=country_list_url, focus_fields=focus_fields)
            config = {
                **config,
                "resolved_country_url": country_list_url,
                "field_map": {
                    "name": "name",
                    "country": "country",
                    "location": "location",
                    "description": "description",
                    "website": "website",
                    "source_url": "source_url",
                    "reference_url": "reference_url",
                    "source_href": "source_href",
                    "admissions_page_link": "admissions_page_link",
                    "admissions_contact": "admissions_contact",
                    "admissions_phone": "admissions_phone",
                    "financials": "financials",
                    "financials_source_url": "financials_source_url",
                    "campus_student_life": "campus_student_life",
                    "campus_student_life_source_url": "campus_student_life_source_url",
                    "housing_availability": "housing_availability",
                    "housing_source_url": "housing_source_url",
                    "immigration_support": "immigration_support",
                    "international_source_url": "international_source_url",
                    "number_of_students": "number_of_students",
                    "student_to_faculty_ratio": "student_to_faculty_ratio",
                    "international_student_ratio": "international_student_ratio",
                    "university_campuses": "university_campuses",
                    "global_rank": "global_rank",
                    "snippet": "snippet",
                    "wikipedia_article_url": "wikipedia_article_url",
                },
                "unique_key_field": "source_href",
                "text_field": "snippet",
            }
            return _bundle_from_rows(source_id=source_id, source_name=source_name, rows=rows, config=config)
        if parser_variant == "ranking_html":
            rows = _extract_unirank_rows(html, country=country)
            normalized_focus_fields = _normalized_focus_fields(focus_fields)
            rows = _enrich_unirank_rows(
                rows,
                country=country,
                config=config,
                referer=url,
                focus_fields=normalized_focus_fields,
            )
            config = {
                **config,
                "field_map": {
                    "name": "name",
                    "country": "country",
                    "location": "location",
                    "description": "description",
                    "website": "website",
                    "source_url": "source_url",
                    "reference_url": "reference_url",
                    "source_href": "source_href",
                    "admissions_page_link": "admissions_page_link",
                    "admissions_contact": "admissions_contact",
                    "admissions_phone": "admissions_phone",
                    "financials": "financials",
                    "financials_source_url": "financials_source_url",
                    "campus_student_life": "campus_student_life",
                    "campus_student_life_source_url": "campus_student_life_source_url",
                    "housing_availability": "housing_availability",
                    "housing_source_url": "housing_source_url",
                    "immigration_support": "immigration_support",
                    "international_source_url": "international_source_url",
                    "snippet": "snippet",
                },
                "unique_key_field": "source_href",
                "text_field": "snippet",
            }
            return _bundle_from_rows(source_id=source_id, source_name=source_name, rows=rows, config=config)
        if parser_variant == "wikipedia_list_html":
            rows = _extract_wikipedia_list_rows(html, country=country, list_url=url)
            rows = _enrich_wikipedia_rows(rows, country=country, config=config, referer=url, focus_fields=focus_fields)
            config = {
                **config,
                "field_map": {
                    "name": "name",
                    "country": "country",
                    "location": "location",
                    "description": "description",
                    "website": "website",
                    "source_url": "source_url",
                    "reference_url": "reference_url",
                    "source_href": "source_href",
                    "admissions_page_link": "admissions_page_link",
                    "admissions_contact": "admissions_contact",
                    "admissions_phone": "admissions_phone",
                    "financials": "financials",
                    "financials_source_url": "financials_source_url",
                    "campus_student_life": "campus_student_life",
                    "campus_student_life_source_url": "campus_student_life_source_url",
                    "housing_availability": "housing_availability",
                    "housing_source_url": "housing_source_url",
                    "immigration_support": "immigration_support",
                    "international_source_url": "international_source_url",
                    "number_of_students": "number_of_students",
                    "student_to_faculty_ratio": "student_to_faculty_ratio",
                    "international_student_ratio": "international_student_ratio",
                    "university_campuses": "university_campuses",
                    "global_rank": "global_rank",
                    "snippet": "snippet",
                    "wikipedia_article_url": "wikipedia_article_url",
                },
                "unique_key_field": "source_href",
                "text_field": "snippet",
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
