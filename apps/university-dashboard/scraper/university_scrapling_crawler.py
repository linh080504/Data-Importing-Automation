#!/usr/bin/env python
from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import time
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from scrapling.fetchers import DynamicFetcher, Fetcher, FetcherSession, StealthyFetcher
except Exception:  # pragma: no cover - fallback is for incomplete local Python envs.
    Fetcher = None
    FetcherSession = None
    DynamicFetcher = None
    StealthyFetcher = None

try:
    from scrapling.parser import Selector
except Exception:  # pragma: no cover - fallback is for incomplete local Python envs.
    Selector = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


CSV_HEADERS = [
    "id",
    "name",
    "location",
    "description",
    "slug",
    "sponsored",
    "website",
    "global_rank",
    "financials",
    "student_loan_available",
    "campus_student_life",
    "number_of_students",
    "student_to_faculty_ratio",
    "international_student_ratio",
    "housing_availability",
    "admissions_contact",
    "admissions_phone",
    "contact_person",
    "admissions_page_link",
    "immigration_support",
    "university_campuses",
]
CRAWLER_VERSION = 2

COUNTRIES = {
    356: {
        "name": "India",
        "prefix": "+91",
        "financials": "INR 50k-250k ($600-3000)",
        "list_pages": [
            "https://en.wikipedia.org/wiki/List_of_institutions_of_higher_education_in_India",
            "https://en.wikipedia.org/wiki/List_of_universities_in_India",
        ],
        "local": True,
    },
    704: {
        "name": "Vietnam",
        "prefix": "+84",
        "financials": "VND 20m-150m ($800-6000)",
        "list_pages": ["https://en.wikipedia.org/wiki/List_of_universities_in_Vietnam"],
        "local": True,
    },
    840: {
        "name": "United States",
        "prefix": "+1",
        "financials": "USD 8k-45k ($8000-45000)",
        "list_pages": ["https://en.wikipedia.org/wiki/List_of_colleges_and_universities_in_the_United_States"],
        "local": False,
    },
    826: {
        "name": "United Kingdom",
        "prefix": "+44",
        "financials": "GBP 9k-28k ($11000-35000)",
        "list_pages": ["https://en.wikipedia.org/wiki/List_of_universities_in_the_United_Kingdom"],
        "local": False,
    },
    124: {
        "name": "Canada",
        "prefix": "+1",
        "financials": "CAD 7k-35k ($5000-26000)",
        "list_pages": ["https://en.wikipedia.org/wiki/List_of_universities_in_Canada"],
        "local": False,
    },
}

SCRAPLING_CONFIG: dict[str, Any] = {
    "fetch_mode": "auto",
    "request_timeout": 8,
    "browser_timeout_ms": 12000,
    "max_official_pages": 8,
    "max_academic_pages": 12,
    "max_browser_fallbacks": 2,
    "skip_guessed_pages_on_failure": True,
    "network_idle": True,
    "disable_resources": True,
    "real_chrome": False,
    "solve_cloudflare": False,
}
HTTP_SESSION: Any = None
REQUESTED_MAJORS: list[str] = []
MAJOR_MODE = "discover"

DENY_OFFICIAL = re.compile(
    r"(wikipedia|wikimedia|wikidata|creativecommons|doi\.org|facebook|twitter|x\.com|linkedin|youtube|instagram|google|archive\.org|toolforge|geohack|openstreetmap|osm\.org|maps?|coordinates?|geonames|worldcat|viaf)",
    re.I,
)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s().-]?)?(?:\(?\d{2,5}\)?[\s().-]?){2,5}\d{3,5}")
MOJIBAKE_RE = re.compile(r"(Ã|Â|Ä|Æ|áº|á»|â€|ï»¿)")
NON_ENGLISH_RE = re.compile(r"[^\x00-\x7F]")
COUNTRY_ALIASES = {
    "India": ["india"],
    "Vietnam": ["vietnam", "viet nam"],
    "United States": ["united states", "usa", "u.s.", "america"],
    "United Kingdom": ["united kingdom", "england", "scotland", "wales", "northern ireland", "uk"],
    "Canada": ["canada"],
}
WIKIDATA_COUNTRY_IDS = {
    "India": "Q668",
    "Vietnam": "Q881",
    "United States": "Q30",
    "United Kingdom": "Q145",
    "Canada": "Q16",
}
VIETNAM_LOCATION_ALIASES = [
    "hanoi",
    "ho chi minh",
    "da nang",
    "danang",
    "hue",
    "can tho",
    "hai phong",
    "haiphong",
    "nha trang",
    "binh duong",
    "hung yen",
    "thai nguyen",
    "lam dong",
    "dong thap",
    "nam dinh",
    "hai duong",
    "vinh",
]


def emit(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def fix_mojibake_text(value: Any) -> str:
    text = "" if value is None else str(value)
    if not MOJIBAKE_RE.search(text):
        return text
    for source_encoding in ("latin1", "cp1252"):
        try:
            repaired = text.encode(source_encoding).decode("utf-8")
        except UnicodeError:
            continue
        if repaired != text:
            return repaired.replace("Â·", "-").replace("\ufeff", "").strip()
    return text.replace("Â·", "-").replace("Â", "").replace("\ufeff", "").strip()


def is_english_safe(value: str, *, allow_symbols: bool = True) -> bool:
    if not value:
        return False
    text = fix_mojibake_text(value)
    if NON_ENGLISH_RE.search(text):
        return False
    letters = re.findall(r"[A-Za-z]", text)
    if len(letters) < 3:
        return False
    if not allow_symbols and re.search(r"[^A-Za-z .,'()&/-]", text):
        return False
    return True


def english_or_blank(value: str, *, allow_symbols: bool = True) -> str:
    text = clean_infobox_value(fix_mojibake_text(value))
    return ascii_text(text) if text else ""


def ascii_text(value: Any) -> str:
    text = fix_mojibake_text(value)
    text = text.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text).strip()


def has_non_ascii(value: str) -> bool:
    return bool(NON_ENGLISH_RE.search(fix_mojibake_text(value or "")))


def add_field_warning(warnings: dict[str, list[str]], field: str, message: str) -> None:
    if not message:
        return
    warnings.setdefault(field, [])
    if message not in warnings[field]:
        warnings[field].append(message)


def english_sentence_score(value: str) -> float:
    text = fix_mojibake_text(value)
    if not text:
        return 0
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    letters = re.findall(r"[A-Za-z]", text)
    return (ascii_chars / max(1, len(text))) * min(1, len(letters) / 40)


def official_description_from_html(body: str) -> str:
    candidates: list[str] = []
    if Selector is not None:
        page = Selector(body)
        candidates.extend(page.css('meta[name="description"]::attr(content)').getall())
        for selector in ["main p::text", "article p::text", "section p::text", ".content p::text", "#content p::text"]:
            text = clean_selector_text(page.css(selector).getall())
            if text:
                candidates.append(text)
    else:
        candidates.extend(re.findall(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', body, re.I))
    for candidate in candidates:
        text = clean_infobox_value(candidate)
        if NON_ENGLISH_RE.search(text):
            continue
        if re.search(r"\b(address|tel|telephone|fax|email|hotline)\b", text, re.I):
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        snippet = " ".join(sentence for sentence in sentences if 40 <= len(sentence) <= 240)[:420]
        if 80 <= len(snippet) <= 420 and not NON_ENGLISH_RE.search(snippet) and english_sentence_score(snippet) > 0.85:
            return snippet
    return ""


def text_from_html(value: str) -> str:
    value = fix_mojibake_text(value)
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<sup[\s\S]*?</sup>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>|<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<span\b[^>]*style=[\"'][^\"']*display\s*:\s*none[^\"']*[\"'][\s\S]*?</span>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return fix_mojibake_text(re.sub(r"\s+", " ", html.unescape(value.replace("&nbsp;", " "))).strip())


def clean_infobox_value(value: str) -> str:
    value = fix_mojibake_text(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\b\d{1,3}°\d{1,2}′\d{1,2}(?:″|&Prime;)?[NSEW]\s+\d{1,3}°\d{1,2}′\d{1,2}(?:″|&Prime;)?[NSEW]\b", "", value)
    value = re.sub(r"\s*/\s*-?\d{1,3}\.\d+;\s*-?\d{1,3}\.\d+", "", value)
    value = re.sub(r"\s*/\s*-?\d{1,3}\.\d+°?[NSEW]?\s*;\s*-?\d{1,3}\.\d+°?[NSEW]?", "", value)
    value = re.sub(r"\s*/\s*-?\d{1,3}\.\d+°?[NSEW]\s+-?\d{1,3}\.\d+°?[NSEW]", "", value)
    value = re.sub(r"\b-?\d{1,3}\.\d+°?[NSEW]\s+-?\d{1,3}\.\d+°?[NSEW]\b", "", value)
    value = re.sub(r"\b-?\d{1,3}\.\d+;\s*-?\d{1,3}\.\d+\b", "", value)
    value = value.replace("\ufeff", " ")
    value = re.sub(r"\s*/\s*/?\s*", " ", value)
    value = re.sub(r"\s+", " ", value)
    return fix_mojibake_text(value.strip(" ,.;"))


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"&", " and ", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")


def fetch_page(url: str):
    if Fetcher is not None:
        content, _, failure, _ = fetch_scrapling_html(url, purpose="wikipedia", allow_browser=False)
        if failure and not content:
            raise RuntimeError(failure)
        return Selector(content, url=url) if Selector is not None else content
    request = Request(url, headers={"User-Agent": "UniversityScraplingCrawler/0.1"})
    with urlopen(request, timeout=20) as response:
        content = response.read().decode("utf-8", "ignore")
        return Selector(content, url=url) if Selector is not None else content


def fetch_html(url: str) -> str:
    page = fetch_page(url)
    return page.get() if hasattr(page, "get") else str(page)


def fetch_official_html(url: str, *, guessed: bool, browser_fallbacks: int) -> tuple[str, str, bool, str]:
    if Fetcher is not None:
        allow_browser = not guessed or not SCRAPLING_CONFIG["skip_guessed_pages_on_failure"]
        body, mode, failure, final_url = fetch_scrapling_html(
            url,
            purpose="official",
            allow_browser=allow_browser,
            browser_fallbacks=browser_fallbacks,
        )
        return body[:420000], failure, mode != "http", final_url
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; UniversityDataCrawler/0.1)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5",
        },
    )
    context = ssl.create_default_context()
    try:
        with urlopen(request, timeout=SCRAPLING_CONFIG["request_timeout"], context=context) as response:
            return response.read(420000).decode("utf-8", "ignore"), "", False, response.geturl()
    except ssl.SSLError:
        insecure_context = ssl._create_unverified_context()
        with urlopen(request, timeout=SCRAPLING_CONFIG["request_timeout"], context=insecure_context) as response:
            return response.read(420000).decode("utf-8", "ignore"), "", False, response.geturl()


def is_wiki_institution_title(title: str) -> bool:
    if not title:
        return False
    if re.match(r"^(List of|Category:|Template:|Help:|File:|Portal:|Wikipedia:)", title, re.I):
        return False
    if re.search(r"Education in|Higher education|Universities in|Colleges in|Rankings of", title, re.I):
        return False
    if re.search(r"^(University system|Collegiate university|Public university|Private university|University college)$", title, re.I):
        return False
    return bool(
        re.search(r"University|College|Institute|School|Academy|Polytechnic|Conservatoire|Seminary|Université|Universidad|Universität", title, re.I)
        or re.search(r"\b(IIT|IIM|AIIMS|NIT|VNU|HUST)\b", title, re.I)
    )


def is_wiki_article_href(href: str) -> bool:
    if not href.startswith("/wiki/"):
        return False
    title = wiki_title_from_href(href)
    if not title:
        return False
    if ":" in href or "#" in href:
        return False
    if re.match(r"^(List of|Lists of|Category|Template|Help|File|Portal|Wikipedia)\b", title, re.I):
        return False
    return True


def clean_selector_text(values: list[str] | Any) -> str:
    return fix_mojibake_text(re.sub(r"\s+", " ", html.unescape(" ".join(str(value) for value in values))).strip())


def response_to_html(response: Any, url: str = "") -> str:
    if response is None:
        return ""
    if hasattr(response, "get"):
        try:
            return str(response.get())
        except Exception:
            pass
    body = getattr(response, "body", None)
    if isinstance(body, bytes):
        encoding = getattr(response, "encoding", None) or "utf-8"
        return body.decode(encoding, "ignore")
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    value = str(response)
    if value.startswith("<") or "<html" in value.lower():
        return value
    return Selector(value, url=url).get() if Selector is not None else value


def response_status(response: Any) -> int:
    try:
        return int(getattr(response, "status", 0) or getattr(response, "status_code", 0) or 0)
    except Exception:
        return 0


def response_url(response: Any, fallback: str) -> str:
    for attribute in ("url", "final_url", "response_url"):
        value = getattr(response, attribute, None)
        if value:
            return str(value)
    return fallback


def looks_useful_html(body: str, *, require_selector: str = "") -> bool:
    if not body or len(body) < 250:
        return False
    if require_selector and Selector is not None:
        try:
            return bool(Selector(body).css(require_selector))
        except Exception:
            return require_selector.lower() in body.lower()
    return bool(re.search(r"<html|<body|<table|<main|<footer|<article|<urlset|<sitemapindex", body, re.I))


def is_script_heavy_or_empty(body: str) -> bool:
    if not body:
        return True
    text = text_from_html(body)
    script_count = len(re.findall(r"<script\b", body, re.I))
    meaningful_tags = len(re.findall(r"<(main|article|section|footer|table|p)\b", body, re.I))
    empty_root = bool(re.search(r'<div[^>]+id=["\'](?:root|app|__next)["\'][^>]*>\s*</div>', body, re.I))
    return empty_root or (script_count >= 12 and meaningful_tags <= 2 and len(text) < 500)


def classify_fetch_failure(error: str, body: str = "") -> str:
    text = f"{error} {body[:500]}".lower()
    if "download is starting" in text:
        return "download_started"
    if "404" in text or "not found" in text:
        return "not_found"
    if "timed out" in text or "timeout" in text or "connection timed" in text:
        return "timeout"
    if "cloudflare" in text or "forbidden" in text or "403" in text or "blocked" in text:
        return "blocked"
    if body and not looks_useful_html(body):
        return "not_html"
    return "browser_failed" if "page.goto" in text or "playwright" in text else "fetch_failed"


def body_is_not_found(body: str) -> bool:
    sample = text_from_html(body)[:1200].lower()
    return bool(re.search(r"\b(404|page not found|not found|the page you requested could not be found)\b", sample))


def scrapling_http_get(url: str) -> Any:
    kwargs = {
        "timeout": SCRAPLING_CONFIG["request_timeout"],
        "retries": 1,
        "retry_delay": 0,
        "stealthy_headers": True,
        "impersonate": "chrome",
        "selector_config": {"adaptive": True, "huge_tree": True},
    }
    if HTTP_SESSION is not None:
        return HTTP_SESSION.get(url, **kwargs)
    if Fetcher is None:
        raise RuntimeError("Scrapling Fetcher is unavailable")
    return Fetcher.get(url, **kwargs)


def scrapling_browser_fetch(url: str, mode: str) -> Any:
    fetcher = StealthyFetcher if mode == "stealthy" else DynamicFetcher
    if fetcher is None:
        raise RuntimeError(f"Scrapling {mode} fetcher is unavailable")
    kwargs: dict[str, Any] = {
        "headless": True,
        "timeout": SCRAPLING_CONFIG["browser_timeout_ms"],
        "network_idle": SCRAPLING_CONFIG["network_idle"],
        "disable_resources": SCRAPLING_CONFIG["disable_resources"],
        "real_chrome": SCRAPLING_CONFIG["real_chrome"],
        "block_ads": True,
        "load_dom": True,
        "selector_config": {"adaptive": True, "huge_tree": True},
        "retries": 1,
        "retry_delay": 0,
    }
    if mode == "stealthy":
        kwargs["solve_cloudflare"] = SCRAPLING_CONFIG["solve_cloudflare"]
        kwargs["block_webrtc"] = True
    return fetcher.fetch(url, **kwargs)


def fetch_scrapling_html(
    url: str,
    *,
    require_selector: str = "",
    purpose: str = "page",
    allow_browser: bool = True,
    browser_fallbacks: int = 0,
) -> tuple[str, str, str, str]:
    mode = SCRAPLING_CONFIG["fetch_mode"]
    tried: list[str] = []

    def attempt(fetch_mode: str) -> tuple[str, int, str]:
        tried.append(fetch_mode)
        if fetch_mode == "http":
            response = scrapling_http_get(url)
            return response_to_html(response, url), response_status(response), response_url(response, url)
        response = scrapling_browser_fetch(url, fetch_mode)
        return response_to_html(response, url), response_status(response), response_url(response, url)

    if mode == "auto":
        modes = ["http"]
        if allow_browser and browser_fallbacks < SCRAPLING_CONFIG["max_browser_fallbacks"]:
            modes.append("stealthy" if SCRAPLING_CONFIG["solve_cloudflare"] else "dynamic")
    else:
        modes = [mode]
    last_error = ""
    for fetch_mode in modes:
        try:
            body, status, final_url = attempt(fetch_mode)
            if status >= 400:
                return body, fetch_mode, "not_found" if status == 404 else "blocked" if status in {401, 403, 429} else "fetch_failed", final_url
            useful = looks_useful_html(body, require_selector=require_selector)
            if useful:
                if fetch_mode != "http":
                    emit("fetch_mode", url=url, purpose=purpose, mode=fetch_mode)
                return body, fetch_mode, "", final_url
            if fetch_mode == "http" and not allow_browser:
                return body, fetch_mode, classify_fetch_failure("", body), final_url
            if fetch_mode == "http" and mode == "auto" and not is_script_heavy_or_empty(body):
                return body, fetch_mode, classify_fetch_failure("", body), final_url
            if fetch_mode == modes[-1]:
                return body, fetch_mode, "" if useful else classify_fetch_failure("", body), final_url
        except Exception as exc:
            last_error = str(exc)
            failure = classify_fetch_failure(last_error)
            if fetch_mode == "http" and failure in {"timeout", "download_started"}:
                return "", fetch_mode, failure, url
            if mode != "auto":
                raise
            continue
    if last_error:
        return "", ",".join(tried), classify_fetch_failure(last_error), url
    return "", ",".join(tried), "fetch_failed", url


class WikiTableLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.table_depth = 0
        self.current_href = ""
        self.current_title = ""
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "table" and "wikitable" in attrs_dict.get("class", ""):
            self.in_table = True
            self.table_depth = 1
        elif self.in_table and tag == "table":
            self.table_depth += 1
        elif self.in_table and tag == "a":
            self.current_href = attrs_dict.get("href", "")
            self.current_title = attrs_dict.get("title", "")
            self.current_text = []

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag == "a" and self.current_href:
            title = self.current_title or wiki_title_from_href(self.current_href) or " ".join(self.current_text)
            href = self.current_href
            if title and href.startswith("/wiki/") and is_wiki_institution_title(title):
                self.links.append((title.strip(), urljoin("https://en.wikipedia.org", href)))
            self.current_href = ""
            self.current_title = ""
            self.current_text = []
        elif self.in_table and tag == "table":
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.in_table = False

    def handle_data(self, data: str) -> None:
        if self.current_href:
            self.current_text.append(data)


def wiki_title_from_href(href: str) -> str:
    if not href.startswith("/wiki/") or ":" in href:
        return ""
    return fix_mojibake_text(unquote(href.replace("/wiki/", "").split("#", 1)[0]).replace("_", " "))


def normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", ascii_text(value).lower()).strip()


def institution_column_index(headers: list[str]) -> int:
    normalized = [normalized_header(header) for header in headers]
    priorities = [
        "english name",
        "university name",
        "institution name",
        "name",
        "member university",
        "member",
        "university system",
        "university",
        "institution",
        "college",
    ]
    for wanted in priorities:
        for index, header in enumerate(normalized):
            if header == wanted:
                return index
    for index, header in enumerate(normalized):
        if any(token in header for token in ("university", "institution", "college", "academy")):
            if not any(noise in header for noise in ("partner", "awarding", "location", "vietnamese")):
                return index
    return -1


def discover_links_from_html(html_text: str, list_url: str, limit: int) -> list[tuple[str, str]]:
    seen: set[str] = set()
    output: list[tuple[str, str]] = []

    def add_link(title: str, href: str) -> None:
        if len(output) >= limit:
            return
        if not is_wiki_article_href(href):
            return
        href_title = wiki_title_from_href(href)
        candidate_title = href_title or title
        if MOJIBAKE_RE.search(candidate_title) and href_title:
            candidate_title = href_title
        candidate_title = fix_mojibake_text(candidate_title)
        if not is_wiki_institution_title(candidate_title):
            return
        url = urljoin("https://en.wikipedia.org", href)
        key = unquote(urlparse(url).path).lower()
        if key in seen:
            return
        seen.add(key)
        output.append((candidate_title.strip(), url))

    if Selector is not None:
        page = Selector(html_text, url=list_url)
        for table in page.css("#mw-content-text table.wikitable, #mw-content-text table"):
            rows = table.css("tr")
            if not rows:
                continue
            headers: list[str] = []
            for row in rows:
                header_cells = row.css("th")
                if len(header_cells) >= 2:
                    headers = [clean_selector_text(cell.css("::text").getall()) for cell in header_cells]
                    if institution_column_index(headers) >= 0:
                        break
            column_index = institution_column_index(headers)
            if column_index < 0:
                continue
            for row in rows:
                cells = row.css("td")
                row_headers = row.css("th")
                if len(cells) + len(row_headers) != len(headers):
                    continue
                effective_index = column_index - len(row_headers)
                if effective_index < 0 or effective_index >= len(cells):
                    continue
                cell = cells[effective_index]
                before_count = len(output)
                for link in cell.css("a"):
                    href = str(link.attrib.get("href", ""))
                    title = str(link.attrib.get("title", "")) or clean_selector_text(link.xpath(".//text()").getall())
                    add_link(title, href)
                    if len(output) >= limit:
                        return output
                if len(output) == before_count:
                    plain_title = clean_selector_text(cell.css("::text").getall())
                    if is_wiki_institution_title(plain_title):
                        synthetic_href = f"/wiki/{quote(plain_title.replace(' ', '_'))}"
                        add_link(plain_title, synthetic_href)
                        if len(output) >= limit:
                            return output
        for item in page.css("#mw-content-text > div > ul > li, #mw-content-text > div > ol > li"):
            for link in item.css("a")[:1]:
                href = str(link.attrib.get("href", ""))
                title = str(link.attrib.get("title", "")) or clean_selector_text(link.xpath(".//text()").getall())
                add_link(title, href)
                if len(output) >= limit:
                    return output
        return output

    parser = WikiTableLinkParser()
    parser.feed(html_text)
    for title, url in parser.links:
        add_link(title, urlparse(url).path)
        if len(output) >= limit:
            return output
    return output


def discover_links(list_url: str, limit: int) -> list[tuple[str, str]]:
    return discover_links_from_html(fetch_html(list_url), list_url, limit)


def wikipedia_search_candidate(title: str, country_name: str) -> str:
    query = f'"{title}" {country_name}'
    api_url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=8&srnamespace=0&srsearch="
        + quote(query)
    )
    try:
        if Fetcher is not None:
            response = scrapling_http_get(api_url)
            payload = json.loads(response_to_html(response, api_url))
        else:
            request = Request(api_url, headers={"User-Agent": "UniversityScraplingCrawler/0.2"})
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8", "ignore"))
    except Exception:
        return ""
    wanted_tokens = {
        token
        for token in re.findall(r"[a-z0-9]{3,}", ascii_text(title).lower())
        if token not in {"the", "and", "university", "college", "institute", "academy"}
    }
    best_title = ""
    best_score = 0.0
    for item in payload.get("query", {}).get("search", []):
        candidate = clean_infobox_value(item.get("title", ""))
        if not is_wiki_institution_title(candidate):
            continue
        candidate_tokens = set(re.findall(r"[a-z0-9]{3,}", ascii_text(candidate).lower()))
        score = len(wanted_tokens & candidate_tokens) / max(1, len(wanted_tokens))
        if score > best_score:
            best_title = candidate
            best_score = score
    if best_score < 0.5:
        return ""
    return f"https://en.wikipedia.org/wiki/{quote(best_title.replace(' ', '_'))}"


def fetch_json_url(url: str) -> dict[str, Any]:
    if Fetcher is not None:
        response = scrapling_http_get(url)
        body = getattr(response, "body", None)
        if isinstance(body, bytes):
            return json.loads(body.decode(getattr(response, "encoding", None) or "utf-8", "ignore"))
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return json.loads(text)
        return json.loads(str(response))
    request = Request(url, headers={"User-Agent": "UniversityScraplingCrawler/0.2"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8", "ignore"))


def wikidata_fallback(title: str, country_name: str) -> tuple[Infobox | None, str]:
    expected_country = WIKIDATA_COUNTRY_IDS.get(country_name)
    if not expected_country:
        return None, ""
    search_url = (
        "https://www.wikidata.org/w/api.php?action=wbsearchentities&language=en&format=json&limit=10&type=item&search="
        + quote(title)
    )
    try:
        results = fetch_json_url(search_url).get("search", [])
    except Exception:
        return None, ""
    wanted_tokens = {
        token
        for token in re.findall(r"[a-z0-9]{3,}", ascii_text(title).lower())
        if token not in {"the", "and", "university", "college", "institute", "academy"}
    }
    ranked: list[tuple[float, str]] = []
    for item in results:
        label = ascii_text(item.get("label", "")).lower()
        description = ascii_text(item.get("description", "")).lower()
        if not re.search(r"university|college|academy|institute|higher education", f"{label} {description}"):
            continue
        candidate_tokens = set(re.findall(r"[a-z0-9]{3,}", label))
        score = len(wanted_tokens & candidate_tokens) / max(1, len(wanted_tokens))
        if country_name.lower() in description:
            score += 0.5
        ranked.append((score, str(item.get("id", ""))))
    for score, entity_id in sorted(ranked, reverse=True):
        if score < 0.5 or not entity_id:
            continue
        try:
            entity = fetch_json_url(
                f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
            )["entities"][entity_id]
        except Exception:
            continue
        claims = entity.get("claims", {})
        countries = {
            claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            for claim in claims.get("P17", [])
        }
        if expected_country not in countries:
            continue
        labels = entity.get("labels", {})
        caption = labels.get("en", {}).get("value") or title
        websites = [
            claim.get("mainsnak", {}).get("datavalue", {}).get("value", "")
            for claim in claims.get("P856", [])
        ]
        inception = ""
        if claims.get("P571"):
            inception = str(
                claims["P571"][0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("time", "")
            )
        students = ""
        if claims.get("P2196"):
            students = str(
                claims["P2196"][0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("amount", "")
            ).lstrip("+")
        return (
            Infobox(
                caption=caption,
                established=first_year(inception),
                students=parse_number(students),
                location_text=country_name,
                website=next((clean_url(str(value)) for value in websites if clean_url(str(value))), ""),
                labels={"wikidata country": country_name},
            ),
            entity_id,
        )
    return None, ""


def find_first_table(html_text: str, class_name: str) -> str:
    table_re = re.compile(r"<table\b[^>]*>[\s\S]*?</table>", re.I)
    for match in table_re.finditer(html_text):
        table = match.group(0)
        if re.search(rf'class=["\'][^"\']*{re.escape(class_name)}', table, re.I):
            return table
    return ""


def first_external_href(value_html: str) -> str:
    match = re.search(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>', value_html, re.I)
    if not match:
        return ""
    href = html.unescape(match.group(1))
    return href if re.match(r"https?://", href, re.I) else ""


def selector_html(node: Any) -> str:
    return node.get() if hasattr(node, "get") else str(node)


def selector_text(node: Any) -> str:
    if hasattr(node, "get"):
        return clean_infobox_value(text_from_html(node.get()))
    return clean_infobox_value(text_from_html(str(node)))


@dataclass
class Infobox:
    caption: str = ""
    type: str = ""
    established: str = ""
    president: str = ""
    students: str = ""
    undergraduates: str = ""
    postgraduates: str = ""
    location_text: str = ""
    campus: str = ""
    website: str = ""
    parent_institution: str = ""
    principal: str = ""
    labels: dict[str, str] | None = None


def country_validation(info: Infobox, country: dict[str, Any], wikipedia_url: str) -> dict[str, Any]:
    country_name = str(country["name"])
    location = clean_infobox_value(info.location_text)
    normalized_location = ascii_text(location).lower()
    aliases = COUNTRY_ALIASES.get(country_name, [country_name.lower()])
    if any(alias in normalized_location for alias in aliases):
        return {
            "status": "verified",
            "reason": f"Wikipedia infobox location identifies {country_name}.",
            "evidenceUrl": wikipedia_url,
            "evidenceText": location,
        }
    if country_name == "Vietnam" and any(alias in normalized_location for alias in VIETNAM_LOCATION_ALIASES):
        return {
            "status": "verified",
            "reason": "Wikipedia infobox location identifies a Vietnamese city.",
            "evidenceUrl": wikipedia_url,
            "evidenceText": location,
        }
    for other_country, other_aliases in COUNTRY_ALIASES.items():
        if other_country == country_name:
            continue
        if any(alias in normalized_location for alias in other_aliases):
            return {
                "status": "rejected",
                "reason": f"Wikipedia infobox location points to {other_country}, not {country_name}.",
                "evidenceUrl": wikipedia_url,
                "evidenceText": location,
            }
    return {
        "status": "list_evidence",
        "reason": f"Accepted from the country list; infobox has no contradictory country evidence.",
        "evidenceUrl": wikipedia_url,
        "evidenceText": location,
    }


def parse_number(value: str) -> str:
    match = re.search(r"[\d,]{3,}", value)
    return match.group(0).replace(",", "") if match else ""


def parse_campus_count(value: str) -> str:
    match = re.search(r"\b(\d{1,3})\s+campuses\b", value, re.I)
    return match.group(1) if match else ""


def parse_student_ratio(value: str) -> str:
    match = re.search(r"\b(\d{1,2})\s*:\s*1\b", value)
    return match.group(1) if match else ""


def parse_international_ratio(value: str) -> str:
    match = re.search(r"\b(\d{1,3})\s*%\s+international", value, re.I)
    return match.group(1) if match else ""


def parse_financials(value: str) -> str:
    if not re.search(r"tuition|fee|fees|financial|cost|hoc\s*phi|chi\s*phi", ascii_text(value), re.I):
        return ""
    match = re.search(r"((?:INR|VND|USD|GBP|CAD|AUD|EUR|JPY|SGD|\$|₹|₫|£|€)\s*\d[\d,.]*(?:\s?[mkK])?(?:\s*[-–]\s*(?:INR|VND|USD|GBP|CAD|AUD|EUR|JPY|SGD|\$|₹|₫|£|€)?\s*\d[\d,.]*(?:\s?[mkK])?)?)", value, re.I)
    return match.group(1).strip() if match else ""


def parse_infobox(page_html: str) -> Infobox:
    info = Infobox()
    info.labels = {}

    if Selector is not None:
        page = Selector(page_html)
        tables = page.css("table.infobox.vcard") or page.css("table.infobox")
        if tables:
            table_node = tables[0]
            captions = table_node.css("caption")
            info.caption = selector_text(captions[0]) if captions else ""
            for row in table_node.css("tr"):
                labels = row.css("th")
                values = row.css("td")
                if not labels or not values:
                    continue
                label = selector_text(labels[0]).lower()
                value_node = values[-1]
                value = selector_text(value_node)
                value_html = selector_html(value_node)
                if not label or not value:
                    continue
                label = fix_mojibake_text(label)
                value = fix_mojibake_text(value)
                info.labels[label] = value
                if label == "type":
                    info.type = value
                elif "established" in label or "founded" in label:
                    info.established = value
                elif "president" in label or "rector" in label or "chancellor" in label:
                    info.president = value
                elif "principal" in label and not info.principal:
                    info.principal = value
                elif "parent institution" in label or "parent" == label:
                    info.parent_institution = value
                elif "undergraduate" in label:
                    info.undergraduates = parse_number(value)
                elif "postgraduate" in label:
                    info.postgraduates = parse_number(value)
                elif "students" in label or "enrol" in label or "enroll" in label:
                    info.students = parse_number(value)
                elif label == "location":
                    info.location_text = value
                elif "campus" in label:
                    info.campus = value
                elif "website" in label:
                    external = value_node.css("a.external::attr(href)").get("") if hasattr(value_node, "css") else ""
                    href = external or first_external_href(value_html)
                    info.website = href if href else value
            return info

    table = find_first_table(page_html, "infobox")
    if not table:
        return info
    caption = re.search(r"<caption\b[^>]*>([\s\S]*?)</caption>", table, re.I)
    info.caption = text_from_html(caption.group(1)) if caption else ""
    for row in re.finditer(r"<tr\b[^>]*>([\s\S]*?)</tr>", table, re.I):
        row_html = row.group(1)
        label_match = re.search(r"<th\b[^>]*>([\s\S]*?)</th>", row_html, re.I)
        value_match = re.search(r"<td\b[^>]*>([\s\S]*?)</td>", row_html, re.I)
        if not label_match or not value_match:
            continue
        label = text_from_html(label_match.group(1)).lower()
        value_html = value_match.group(1)
        value = text_from_html(value_html)
        label = fix_mojibake_text(label)
        value = fix_mojibake_text(value)
        info.labels[label] = value
        if label == "type":
            info.type = value
        elif "established" in label or "founded" in label:
            info.established = value
        elif any(word in label for word in ["president", "rector", "chancellor"]):
            info.president = value
        elif "principal" in label and not info.principal:
            info.principal = value
        elif "parent institution" in label or label == "parent":
            info.parent_institution = value
        elif "undergraduate" in label:
            info.undergraduates = parse_number(value)
        elif "postgraduate" in label:
            info.postgraduates = parse_number(value)
        elif "students" in label or "enrol" in label or "enroll" in label:
            info.students = parse_number(value)
        elif label == "location":
            info.location_text = value
        elif "campus" in label:
            info.campus = value
        elif "website" in label:
            info.website = first_external_href(value_html) or value
    return info


def first_year(*values: str) -> str:
    for value in values:
        match = re.search(r"\b(18|19|20)\d{2}\b", value or "")
        if match:
            return match.group(0)
    return ""


def clean_url(value: str) -> str:
    value = value.strip()
    if value.startswith("//"):
        value = f"https:{value}"
    if not re.match(r"https?://", value, re.I):
        return ""
    return "" if DENY_OFFICIAL.search(value) else value


def normalized_host(value: str) -> str:
    try:
        return (urlparse(value).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def same_official_site(left: str, right: str) -> bool:
    left_host = normalized_host(left)
    right_host = normalized_host(right)
    if not left_host or not right_host:
        return False
    return (
        left_host == right_host
        or left_host.endswith(f".{right_host}")
        or right_host.endswith(f".{left_host}")
    )


def canonical_homepage(requested_url: str, final_url: str) -> str:
    chosen = clean_url(final_url) or clean_url(requested_url)
    if not chosen:
        return ""
    parsed = urlparse(chosen)
    scheme = "https" if parsed.scheme in {"http", "https"} else parsed.scheme
    return f"{scheme}://{parsed.netloc}/"


def normalize_phone(raw: str, prefix: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.startswith("+") and len(cleaned) >= 8:
        return cleaned
    if 8 <= len(cleaned) <= 14:
        return prefix + cleaned.lstrip("0")
    return ""


def page_text_from_html(body: str) -> str:
    if Selector is not None:
        page = Selector(body)
        return clean_infobox_value(clean_selector_text(page.css("body ::text").getall()))
    return clean_infobox_value(text_from_html(body))


def join_origin_path(origin: str, path: str) -> str:
    return urljoin(f"{origin.rstrip('/')}/", path.lstrip("/"))


def official_candidate_paths(origin: str, homepage: str) -> list[dict[str, Any]]:
    paths = [
        {"url": homepage, "guessed": False},
        {"url": join_origin_path(origin, "contact"), "guessed": True},
        {"url": join_origin_path(origin, "lien-he"), "guessed": True},
        {"url": join_origin_path(origin, "admissions"), "guessed": True},
        {"url": join_origin_path(origin, "tuyen-sinh"), "guessed": True},
        {"url": join_origin_path(origin, "apply"), "guessed": True},
        {"url": join_origin_path(origin, "about"), "guessed": True},
        {"url": join_origin_path(origin, "gioi-thieu"), "guessed": True},
        {"url": join_origin_path(origin, "dao-tao"), "guessed": True, "academic": True},
        {"url": join_origin_path(origin, "chuong-trinh-dao-tao"), "guessed": True, "academic": True},
        {"url": join_origin_path(origin, "nganh-hoc"), "guessed": True, "academic": True},
        {"url": join_origin_path(origin, "sitemap.xml"), "guessed": True, "sitemap": True},
    ]
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        if path["url"] not in seen:
            seen.add(path["url"])
            output.append(path)
    return output


def find_official_links(body: str, base_url: str, origin: str) -> list[str]:
    links: list[str] = []
    if Selector is not None:
        page = Selector(body)
        candidates = [
            (
                str(link.attrib.get("href", "")),
                clean_selector_text(link.xpath(".//text()").getall()),
            )
            for link in page.css("a[href]")
        ]
    else:
        candidates = [
            (match.group(1), text_from_html(match.group(2)))
            for match in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', body, re.I)
        ]
    for href, link_text in candidates:
        full = urljoin(base_url, html.unescape(str(href)))
        if not same_official_site(full, origin):
            continue
        searchable = f"{full} {ascii_text(link_text)}"
        if re.search(
            r"admission|apply|contact|about|campus|locations?|tuition|fees|financial|student-life|housing|"
            r"accommodation|academic|program|programme|degree|curriculum|department|faculty|major|"
            r"dao-tao|chuong-trinh|nganh-hoc|tuyen-sinh|hoc-phi|gioi-thieu|lien-he|co-so|ky-tuc-xa",
            searchable,
            re.I,
        ):
            if full not in links:
                links.append(full)
    return links[:40]


def is_academic_offering_url(url: str) -> bool:
    if re.search(r"/news/|announcement|scholarship|sponsor|exchange|cooperation|doi-tac|tin-tuc|thong-bao", url, re.I):
        return False
    return bool(
        re.search(
            r"academic|program|programme|degree|curriculum|department|faculty|school|major|undergraduate|"
            r"graduate|education|training|dao-tao|chuong-trinh|nganh-hoc|khoa-hoc|khoa/",
            url,
            re.I,
        )
    )


def academic_text_from_html(body: str) -> str:
    if Selector is None:
        return clean_infobox_value(text_from_html(body))
    page = Selector(body)
    selectors = [
        "main ::text",
        "article ::text",
        "[role='main'] ::text",
        ".main-content ::text",
        ".page-content ::text",
        "#content ::text",
    ]
    for selector in selectors:
        values = page.css(selector).getall()
        text = clean_infobox_value(clean_selector_text(values))
        if len(text) >= 80:
            return text
    return ""


MAJOR_NOISE_RE = re.compile(
    r"\b(click here|read more|learn more|view details|admission|apply now|news|event|contact|home|"
    r"objective|learning outcome|training code|faculty|department|school|university|curriculum)\b",
    re.I,
)
SINGLE_WORD_MAJORS = {
    "Accounting",
    "Architecture",
    "Biology",
    "Biotechnology",
    "Chemistry",
    "Dentistry",
    "Economics",
    "Finance",
    "Law",
    "Management",
    "Mathematics",
    "Medicine",
    "Nursing",
    "Pharmacy",
    "Physics",
    "Psychology",
    "Sociology",
}
MAJOR_SIGNAL_RE = re.compile(
    r"\b(engineering|technology|science|management|economics|business|architecture|medicine|"
    r"pharmacy|chemistry|physics|mathematics|biology|biotechnology|informatics|computer|"
    r"communication|environment|construction|language|law|education|design|accounting|finance|"
    r"tourism|logistics|agriculture|nursing|dentistry|psychology|sociology|international studies)\b",
    re.I,
)


def normalize_major_candidate(value: str) -> str:
    candidate = clean_infobox_value(value)
    candidate = re.sub(r"^\s*(?:no\.?\s*)?\d{1,3}[\s.):-]+", "", candidate, flags=re.I)
    candidate = re.sub(r"\s+(?:click here|details?|view)\s*$", "", candidate, flags=re.I)
    candidate = re.sub(r"\s+\d{6,8}\s*$", "", candidate)
    candidate = ascii_text(candidate).strip(" -:;,")
    if not 3 <= len(candidate) <= 120 or not 1 <= len(candidate.split()) <= 14:
        return ""
    if re.fullmatch(r"[\d\W_]+", candidate) or MAJOR_NOISE_RE.fullmatch(candidate):
        return ""
    if re.search(r"\b(students?|faculty|department|school|university|center|centre|news|mission|organization)\b", candidate, re.I):
        return ""
    if len(candidate.split()) == 1 and candidate.title() not in SINGLE_WORD_MAJORS:
        return ""
    if not MAJOR_SIGNAL_RE.search(candidate):
        return ""
    return candidate.title() if candidate.isupper() else candidate


def academic_url_priority(url: str) -> tuple[int, int]:
    if re.search(r"program|programme|curriculum|training|degree|major|undergraduate|graduate|dao-tao|chuong-trinh|nganh-hoc", url, re.I):
        priority = 0
    elif re.search(r"academic|education", url, re.I):
        priority = 1
    elif re.search(r"faculty|department|school", url, re.I):
        priority = 2
    else:
        priority = 3
    if re.search(r"/news/|student|mission|organization|quality-assurance|announcement|scholarship|sponsor", url, re.I):
        priority += 5
    return priority, len(url)


def is_partner_or_news_page(url: str, text: str, institution_name: str) -> bool:
    sample = ascii_text(text)[:5000].lower()
    if re.search(r"/news/|announcement|scholarship|sponsor|exchange|cooperation|doi-tac|tin-tuc|thong-bao", url, re.I):
        return True
    institution_tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z]{4,}", ascii_text(institution_name))
        if token.lower() not in {"university", "college", "institute", "academy", "vietnam"}
    }
    foreign_partner = re.search(
        r"\b(partner university|in cooperation with|exchange program|scholarship program|host university)\b",
        sample,
    )
    has_identity = not institution_tokens or any(token in sample for token in institution_tokens)
    return bool(foreign_partner and not has_identity)


def official_identity_validation(
    institution_name: str,
    homepage_url: str,
    homepage_text: str,
    country: dict[str, Any],
    checked: list[str],
) -> dict[str, str]:
    if not checked:
        return {
            "status": "unreachable",
            "reason": "Official website came from the Wikipedia infobox but no usable page was fetched.",
            "canonicalUrl": canonical_homepage(homepage_url, homepage_url),
        }
    normalized_name = ascii_text(institution_name).lower()
    normalized_text = ascii_text(homepage_text).lower()
    host = normalized_host(checked[0])
    meaningful_tokens = [
        token
        for token in re.findall(r"[a-z]{4,}", normalized_name)
        if token not in {"university", "college", "institute", "academy", "vietnam", "national"}
    ]
    token_matches = sum(1 for token in set(meaningful_tokens) if token in normalized_text)
    acronym = "".join(
        word[0]
        for word in re.findall(r"[a-z]+", normalized_name)
        if word not in {"of", "and", "the", "university", "college", "institute", "academy", "vietnam"}
    )
    host_identity = bool(acronym and len(acronym) >= 3 and acronym in host.replace("-", ""))
    content_identity = token_matches >= 2 and bool(
        re.search(r"\b(university|college|institute|academy|truong dai hoc|hoc vien)\b", normalized_text)
    )
    country_name = str(country["name"])
    education_domain = (
        (country_name == "Vietnam" and host.endswith(".edu.vn"))
        or (country_name == "India" and (host.endswith(".ac.in") or host.endswith(".edu.in")))
        or (country_name == "United Kingdom" and host.endswith(".ac.uk"))
        or (country_name == "Canada" and host.endswith(".ca"))
        or (country_name == "United States" and host.endswith(".edu"))
    )
    status = "verified" if content_identity or host_identity or education_domain else "rejected"
    return {
        "status": status,
        "reason": "Official website identity matched the institution or a country education domain."
        if status == "verified"
        else "Fetched website did not provide enough identity evidence for this institution.",
        "canonicalUrl": canonical_homepage(homepage_url, checked[0]),
    }


def extract_discovered_major_matches(body: str, source_url: str) -> list[dict[str, str]]:
    if Selector is None:
        return []
    page = Selector(body)
    matches: list[dict[str, str]] = []
    selectors = [
        "table tr",
        "main li",
        "article li",
        ".program",
        ".programme",
        ".degree",
        ".major",
        ".course",
        "[class*='program']",
        "[class*='programme']",
    ]
    seen: set[str] = set()
    for selector in selectors:
        for node in page.css(selector):
            cells = [clean_selector_text(cell.css("::text").getall()) for cell in node.css("th, td")]
            texts = [text for text in cells if text] or [clean_selector_text(node.css("::text").getall())]
            href = str(node.css("a::attr(href)").get() or "")
            evidence_url = urljoin(source_url, html.unescape(href)) if href else source_url
            for text in texts[:3]:
                candidate = normalize_major_candidate(text)
                key = candidate.lower()
                if not candidate or key in seen:
                    continue
                seen.add(key)
                code_match = re.search(r"\b\d{6,8}\b", " ".join(texts))
                matches.append(
                    {
                        "majorName": candidate,
                        "sourceUrl": evidence_url,
                        "sourceType": "academic_table" if selector == "table tr" else "program_page",
                        "programCode": code_match.group(0) if code_match else "",
                        "evidenceText": ascii_text(text)[:240],
                    }
                )
    return matches


def extract_contact_person(text: str) -> str:
    text = fix_mojibake_text(text)
    patterns = [
        r"(?:Admissions? Officer|Head of Admissions?|Admissions? Contact|Contact Person|International Office)[:\s-]+([A-Z][A-Za-z .'-]{2,80})",
        r"([A-Z][A-Za-z .'-]{3,80})\s+(?:Admissions? Officer|Head of Admissions?|International Office)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidate = clean_infobox_value(match.group(1))
            if 2 <= len(candidate.split()) <= 8 and is_english_safe(candidate, allow_symbols=False) and not re.search(r"email|phone|address|campus|office|department", candidate, re.I):
                return fix_mojibake_text(candidate)
    return ""


def extract_campus_count(text: str) -> str:
    normalized = ascii_text(text)
    explicit = parse_campus_count(normalized)
    if explicit:
        return explicit
    vietnamese = re.search(r"\b(\d{1,3})\s+co\s+so\b", normalized, re.I)
    if vietnamese:
        return vietnamese.group(1)
    one_match = re.search(r"\b(one|single|main)\s+campus\b|\bco\s+so\s+chinh\b", normalized, re.I)
    if one_match:
        return "1"
    campus_names = set()
    for match in re.finditer(r"\b([A-ZÀ-Ỵ][A-Za-zÀ-ỹ0-9 .'-]{2,80}\s+Campus)\b", text):
        campus_names.add(clean_infobox_value(match.group(1)).lower())
    return str(len(campus_names)) if len(campus_names) >= 2 else ""


def inspect_official_site(url: str, country: dict[str, Any], institution_name: str = "") -> dict[str, Any]:
    if not clean_url(url):
        return {
            "emails": [],
            "phones": [],
            "admissions": "",
            "checked": [],
            "failures": [],
            "stats": {"checked": 0, "skipped": 0, "browserFallbacks": 0},
            "academic_stats": {"checked": 0, "discovered": 0, "extracted": 0},
            "major_matches": [],
            "has_housing": False,
            "contact_person": "",
            "financials": "",
            "campus_count": "",
            "student_life": "",
            "description": "",
            "field_sources": {},
            "field_evidence": {},
            "official_validation": {"status": "missing", "reason": "No official website URL was available."},
        }
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    pages = official_candidate_paths(origin, url)
    emails: list[str] = []
    phones: list[str] = []
    admissions = ""
    checked: list[str] = []
    has_housing = False
    contact_person = ""
    financials = ""
    campus_count = ""
    student_life = ""
    description = ""
    field_sources: dict[str, str] = {}
    field_evidence: dict[str, dict[str, str]] = {}
    major_matches: list[dict[str, str]] = []
    failures: list[dict[str, Any]] = []
    browser_fallbacks = 0
    skipped = 0
    started_at = time.monotonic()
    homepage_text = ""
    enrichment_checked = 0
    academic_checked = 0
    academic_discovered: set[str] = set()
    index = 0
    while index < len(pages):
        if time.monotonic() - started_at >= 45:
            failures.append({"url": url, "reason": "institution_budget_exceeded", "guessed": False, "browserAttempted": browser_fallbacks > 0})
            skipped += max(0, len(pages) - index)
            break
        page_item = pages[index]
        index += 1
        page = str(page_item["url"])
        guessed = bool(page_item.get("guessed"))
        is_academic = bool(page_item.get("academic")) or is_academic_offering_url(page)
        if is_academic:
            if academic_checked >= SCRAPLING_CONFIG["max_academic_pages"]:
                skipped += 1
                continue
        elif enrichment_checked >= SCRAPLING_CONFIG["max_official_pages"]:
            skipped += 1
            continue
        try:
            body, failure, used_browser, final_url = fetch_official_html(
                page,
                guessed=guessed,
                browser_fallbacks=browser_fallbacks,
            )
            if used_browser:
                browser_fallbacks += 1
        except Exception as exc:
            reason = classify_fetch_failure(str(exc))
            failures.append({"url": page, "reason": reason, "guessed": guessed, "browserAttempted": False})
            skipped += 1
            if page == url and not guessed:
                skipped += max(0, len(pages) - index)
                break
            continue
        if failure and not looks_useful_html(body):
            failures.append({"url": page, "reason": failure, "guessed": guessed, "browserAttempted": used_browser})
            skipped += 1
            if page == url and not guessed:
                skipped += max(0, len(pages) - index)
                break
            continue
        if guessed and body_is_not_found(body):
            failures.append({"url": page, "reason": "not_found", "guessed": guessed, "browserAttempted": used_browser})
            skipped += 1
            continue
        if not same_official_site(final_url, origin):
            failures.append({"url": page, "reason": "redirect_domain_mismatch", "guessed": guessed, "browserAttempted": used_browser})
            skipped += 1
            continue
        canonical = canonical_homepage(url, final_url)
        if canonical and page == url:
            origin = f"{urlparse(canonical).scheme}://{urlparse(canonical).netloc}"
            for candidate in official_candidate_paths(origin, canonical):
                if not any(item["url"] == candidate["url"] for item in pages):
                    pages.append(candidate)
        page = final_url or page
        checked.append(page)
        if is_academic:
            academic_checked += 1
        else:
            enrichment_checked += 1
        text = page_text_from_html(body)
        if not homepage_text:
            homepage_text = text
        if is_academic and is_partner_or_news_page(page, text, institution_name):
            failures.append({"url": page, "reason": "partner_or_news_page", "guessed": guessed, "browserAttempted": used_browser})
            skipped += 1
            continue
        if page_item.get("sitemap") or re.search(r"<urlset|<sitemapindex", body, re.I):
            sitemap_links = [
                clean_infobox_value(value)
                for value in re.findall(r"<loc[^>]*>([\s\S]*?)</loc>", body, re.I)
            ]
            academic_links = sorted(
                [
                    link
                    for link in sitemap_links
                    if same_official_site(link, origin) and is_academic_offering_url(link)
                ],
                key=academic_url_priority,
            )[:40]
            academic_discovered.update(academic_links)
            for link in reversed(academic_links):
                if not any(item["url"] == link for item in pages):
                    pages.insert(index, {"url": link, "guessed": False, "academic": True})
            continue
        discovered_links = find_official_links(body, page, origin)
        academic_links = sorted(
            [link for link in discovered_links if is_academic_offering_url(link)],
            key=academic_url_priority,
        )
        academic_discovered.update(academic_links)
        other_links = [link for link in discovered_links if link not in academic_links]
        insert_at = index
        for link in academic_links:
            if not any(item["url"] == link for item in pages):
                pages.insert(insert_at, {"url": link, "guessed": False, "academic": True})
                insert_at += 1
        for link in other_links:
            if not any(item["url"] == link for item in pages):
                pages.append({"url": link, "guessed": False, "academic": False})
        for match in extract_major_document_matches(body, page, origin):
            if match not in major_matches:
                major_matches.append(match)
        if is_academic:
            academic_text = academic_text_from_html(body)
            for match in extract_major_matches(academic_text, page):
                if match not in major_matches:
                    major_matches.append(match)
            if MAJOR_MODE == "discover":
                for match in extract_discovered_major_matches(body, page):
                    if not any(
                        existing["majorName"].lower() == match["majorName"].lower()
                        for existing in major_matches
                    ):
                        major_matches.append(match)
        new_emails = [email.lower() for email in EMAIL_RE.findall(text)]
        emails.extend(new_emails)
        if new_emails and "admissions_contact" not in field_sources:
            field_sources["admissions_contact"] = page
            field_evidence["admissions_contact"] = {
                "sourceUrl": page,
                "evidenceText": new_emails[0],
                "rule": "official_page.email",
            }
        new_phones = [phone for phone in (normalize_phone(item, country["prefix"]) for item in PHONE_RE.findall(text)) if phone]
        phones.extend(new_phones)
        if new_phones and "admissions_phone" not in field_sources:
            field_sources["admissions_phone"] = page
            field_evidence["admissions_phone"] = {
                "sourceUrl": page,
                "evidenceText": new_phones[0],
                "rule": "official_page.phone",
            }
        if not admissions:
            link = re.search(
                r'<a\b[^>]*href=["\']([^"\']*(admission|apply|enrol|enroll|tuyen-sinh|dang-ky)[^"\']*)["\']',
                body,
                re.I,
            )
            admissions = urljoin(page, html.unescape(link.group(1))) if link else ""
            if admissions:
                field_sources["admissions_page_link"] = page
                field_evidence["admissions_page_link"] = {
                    "sourceUrl": page,
                    "evidenceText": admissions,
                    "rule": "official_page.admissions_link",
                }
        if re.search(r"hostel|housing|residence|dormitory|accommodation|ky-tuc-xa|ki-tuc-xa", ascii_text(body), re.I):
            has_housing = True
            field_sources.setdefault("housing_availability", page)
            field_evidence.setdefault(
                "housing_availability",
                {"sourceUrl": page, "evidenceText": "Housing/accommodation keyword found.", "rule": "official_page.housing"},
            )
        if not contact_person:
            contact_person = extract_contact_person(text)
            if contact_person:
                field_sources["contact_person"] = page
                field_evidence["contact_person"] = {
                    "sourceUrl": page,
                    "evidenceText": contact_person,
                    "rule": "official_page.contact_person",
                }
        if not financials:
            financials = parse_financials(text)
            if financials:
                field_sources["financials"] = page
                field_evidence["financials"] = {
                    "sourceUrl": page,
                    "evidenceText": financials,
                    "rule": "official_page.fees",
                }
        if not campus_count:
            campus_count = extract_campus_count(text)
            if campus_count:
                field_sources["university_campuses"] = page
                field_evidence["university_campuses"] = {
                    "sourceUrl": page,
                    "evidenceText": campus_count,
                    "rule": "official_page.campus_count",
                }
        if not student_life:
            student_life = facilities(text)
            if student_life:
                field_sources["campus_student_life"] = page
                field_evidence["campus_student_life"] = {
                    "sourceUrl": page,
                    "evidenceText": student_life,
                    "rule": "official_page.facilities",
                }
        if not description and (re.search(r"\b(about|overview)\b", page, re.I) or page == url):
            description = official_description_from_html(body)
            if description:
                field_sources["description"] = page
                field_evidence["description"] = {
                    "sourceUrl": page,
                    "evidenceText": description[:240],
                    "rule": "official_page.description",
                }
    official_validation = official_identity_validation(institution_name, url, homepage_text, country, checked)
    if official_validation["status"] == "rejected":
        emails = []
        phones = []
        admissions = ""
        has_housing = False
        contact_person = ""
        financials = ""
        campus_count = ""
        student_life = ""
        description = ""
        field_sources = {}
        field_evidence = {}
        major_matches = []
    return {
        "emails": list(dict.fromkeys(emails))[:5],
        "phones": list(dict.fromkeys(phones))[:5],
        "admissions": admissions,
        "checked": checked,
        "failures": failures[:20],
        "stats": {"checked": len(checked), "skipped": skipped, "browserFallbacks": browser_fallbacks},
        "academic_stats": {
            "checked": academic_checked,
            "discovered": len(academic_discovered),
            "extracted": len(major_matches),
        },
        "major_matches": major_matches,
        "has_housing": has_housing,
        "contact_person": contact_person,
        "financials": financials,
        "campus_count": campus_count,
        "student_life": student_life,
        "description": description,
        "field_sources": field_sources,
        "field_evidence": field_evidence,
        "official_validation": official_validation,
    }


def estimate_students(info: Infobox, text: str) -> tuple[str, bool]:
    if info.students:
        return info.students, False
    total = (int(info.undergraduates or 0) + int(info.postgraduates or 0))
    if total:
        return str(total), False
    return "", False


def facilities(text: str) -> str:
    normalized = ascii_text(text)
    found = []
    for pattern, label in [
        (r"library|thu vien", "Library"),
        (r"laborator|phong thi nghiem", "Labs"),
        (r"research|nghien cuu", "Research centers"),
        (r"sport|the thao", "Sports facilities"),
        (r"hostel|housing|residence|dormitory|ky tuc xa", "Housing"),
        (r"club|societ|cau lac bo", "Student clubs"),
        (r"canteen|cafeteria|can tin", "Cafeteria"),
    ]:
        if re.search(pattern, normalized, re.I):
            found.append(label)
    return ", ".join(found[:6])


def extract_major_matches(text: str, source_url: str) -> list[dict[str, str]]:
    if MAJOR_MODE != "verify" or not REQUESTED_MAJORS or not re.search(r"\b(program|programme|degree|major|curriculum|department|faculty|school|course)\b", text, re.I):
        return []
    normalized = re.sub(r"\s+", " ", text)
    matches: list[dict[str, str]] = []
    for major in REQUESTED_MAJORS:
        clean_major = clean_infobox_value(major)
        if not clean_major:
            continue
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(clean_major)}(?![A-Za-z0-9])", normalized, re.I):
            matches.append({"majorName": ascii_text(clean_major), "sourceUrl": source_url, "sourceType": "program_page"})
    return matches


def extract_major_document_matches(body: str, base_url: str, origin: str) -> list[dict[str, str]]:
    if Selector is None:
        return []
    page = Selector(body)
    matches: list[dict[str, str]] = []
    for link in page.css("a[href]"):
        href = str(link.attrib.get("href", ""))
        full = urljoin(base_url, html.unescape(href))
        parsed = urlparse(full)
        if f"{parsed.scheme}://{parsed.netloc}" != origin:
            continue
        if not re.search(r"\.(pdf|docx?|xlsx?)(?:$|[?#])|curriculum|program|programme|degree|major", full, re.I):
            continue
        context = clean_selector_text(
            link.xpath(
                "ancestor::tr[1]//text() | ancestor::li[1]//text() | ancestor::article[1]//text() | ancestor::section[1]//text() | .//text()"
            ).getall()
        )
        if not re.search(r"\b(program|programme|degree|major|curriculum|training|education)\b", context, re.I):
            continue
        candidates = REQUESTED_MAJORS if MAJOR_MODE == "verify" else [context]
        for major in candidates:
            matched_major = ascii_text(major) if MAJOR_MODE == "verify" else normalize_major_candidate(major)
            if matched_major and (
                MAJOR_MODE == "discover"
                or re.search(rf"(?<![A-Za-z0-9]){re.escape(major)}(?![A-Za-z0-9])", context, re.I)
            ):
                match = {
                    "majorName": matched_major,
                    "sourceUrl": full,
                    "sourceType": "official_document",
                    "evidenceText": ascii_text(context)[:240],
                }
                if match not in matches:
                    matches.append(match)
    return matches


def make_description(title: str, country: dict[str, Any], info: Infobox, page_text: str) -> str:
    year = first_year(info.established, page_text)
    parts = [english_or_blank(title)]
    if is_english_safe(info.type):
        parts.append(f"is a {info.type}")
    else:
        parts.append("is an institution")
    if info.parent_institution and is_english_safe(info.parent_institution):
        parts.append(f"affiliated with {info.parent_institution}")
    if info.location_text and is_english_safe(info.location_text):
        parts.append(f"located in {info.location_text}")
    else:
        parts.append(f"listed in {country['name']}")
    if year:
        parts.append(f"established or first recorded in {year}")
    if info.campus and len(info.campus) < 140 and is_english_safe(info.campus):
        parts.append(f"campus: {info.campus}")
    return clean_infobox_value(re.sub(r"\s+", " ", ". ".join(parts)).strip())[:420]


class CountryMismatchError(ValueError):
    def __init__(self, validation: dict[str, Any]) -> None:
        super().__init__(validation["reason"])
        self.validation = validation


def build_record(title: str, url: str, country: dict[str, Any], country_code: int, slug_counts: dict[str, int]) -> dict[str, Any]:
    title = fix_mojibake_text(title)
    candidate_url = url
    wikidata_id = ""
    page_html = fetch_html(url)
    info = parse_infobox(page_html)
    if not info.caption and not info.labels:
        resolved_url = wikipedia_search_candidate(title, country["name"])
        if resolved_url and resolved_url != url:
            page_html = fetch_html(resolved_url)
            info = parse_infobox(page_html)
            if info.caption or info.labels:
                url = resolved_url
        if not info.caption and not info.labels:
            info, wikidata_id = wikidata_fallback(title, country["name"])
            if info is None:
                raise ValueError("No Wikipedia infobox or country-verified Wikidata entity found")
    page_text = text_from_html(page_html)
    primary_source_url = f"https://www.wikidata.org/wiki/{wikidata_id}" if wikidata_id else url
    validation = country_validation(info, country, primary_source_url)
    if validation["status"] == "rejected":
        raise CountryMismatchError(validation)
    official_url = clean_url(info.website)
    official = inspect_official_site(official_url, country, info.caption or title)
    official_url = official["official_validation"].get("canonicalUrl") or official_url
    info.caption = fix_mojibake_text(info.caption)
    info.location_text = fix_mojibake_text(info.location_text)
    info.campus = fix_mojibake_text(info.campus)
    info.president = fix_mojibake_text(info.president)
    info.principal = fix_mojibake_text(info.principal)
    info.parent_institution = fix_mojibake_text(info.parent_institution)
    raw_display_title = clean_infobox_value(info.caption) or clean_infobox_value(title) or wiki_title_from_href(urlparse(url).path)
    display_title = english_or_blank(raw_display_title) or ascii_text(raw_display_title) or "University"
    base_slug = slugify(f"{display_title}-{country['name']}")
    slug_counts[base_slug] = slug_counts.get(base_slug, 0) + 1
    slug = base_slug if slug_counts[base_slug] == 1 else f"{base_slug}-{slug_counts[base_slug]}"
    estimated_fields: list[str] = []
    students, _ = estimate_students(info, page_text)
    life = facilities(info.campus) or official["student_life"]
    labels_text = " ".join((info.labels or {}).values())
    ratio = parse_student_ratio(labels_text)
    international_ratio = parse_international_ratio(labels_text)
    campus_count = parse_campus_count(info.campus) or official["campus_count"]
    financials = parse_financials(labels_text) or official["financials"]
    raw_wiki_contact_person = clean_infobox_value(info.president or info.principal)
    wiki_contact_person = english_or_blank(raw_wiki_contact_person, allow_symbols=False)
    raw_contact_person = official["contact_person"] or raw_wiki_contact_person
    contact_person = official["contact_person"] or wiki_contact_person
    description = fix_mojibake_text(make_description(display_title, country, info, page_text))
    if official["description"]:
        description = ascii_text(official["description"])
    raw_description = official["description"] or description

    csv = {header: "" for header in CSV_HEADERS}
    csv.update(
        {
            "id": "",
            "name": ascii_text(f"{display_title}, {country['name']}" if country["name"] not in display_title else display_title),
            "location": str(country_code),
            "description": ascii_text(description),
            "slug": slug,
            "sponsored": "0",
            "website": official_url,
            "global_rank": "",
            "financials": ascii_text(financials),
            "student_loan_available": "0",
            "campus_student_life": ascii_text(life),
            "number_of_students": students,
            "student_to_faculty_ratio": ratio,
            "international_student_ratio": international_ratio,
            "housing_availability": "1"
            if official["has_housing"] or re.search(r"hostel|housing|residence|dormitory|ky tuc xa", ascii_text(page_text), re.I)
            else "0",
            "admissions_contact": official["emails"][0] if official["emails"] else "",
            "admissions_phone": official["phones"][0] if official["phones"] else "",
            "contact_person": ascii_text(contact_person),
            "admissions_page_link": official["admissions"],
            "immigration_support": "0",
            "university_campuses": campus_count,
        }
    )
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    field_sources = dict(official["field_sources"])
    field_evidence = dict(official["field_evidence"])
    field_sources.update(
        {
            "name": primary_source_url,
            "location": validation["evidenceUrl"],
            "slug": primary_source_url,
            "website": primary_source_url if official_url else "",
        }
    )
    field_evidence.update(
        {
            "name": {
                "sourceUrl": primary_source_url,
                "evidenceText": raw_display_title,
                "rule": "wikidata.label" if wikidata_id else "wikipedia.infobox_title",
            },
            "location": {
                "sourceUrl": validation["evidenceUrl"],
                "evidenceText": validation["evidenceText"],
                "rule": f"country.{validation['status']}",
            },
            "slug": {"sourceUrl": primary_source_url, "evidenceText": slug, "rule": "generated.unique_slug"},
        }
    )
    if official_url:
        field_evidence["website"] = {
            "sourceUrl": primary_source_url,
            "evidenceText": official_url,
            "rule": "wikidata.official_website" if wikidata_id else "wikipedia.infobox_website",
        }
    if description:
        field_sources.setdefault("description", official["field_sources"].get("description") or primary_source_url)
        field_evidence.setdefault(
            "description",
            {"sourceUrl": field_sources["description"], "evidenceText": description[:240], "rule": "evidence.summary"},
        )
    if students:
        field_sources.setdefault("number_of_students", primary_source_url)
        field_evidence.setdefault(
            "number_of_students",
            {
                "sourceUrl": primary_source_url,
                "evidenceText": students,
                "rule": "wikidata.student_count" if wikidata_id else "wikipedia.infobox_students",
            },
        )
    if ratio:
        field_sources.setdefault("student_to_faculty_ratio", url)
        field_evidence.setdefault(
            "student_to_faculty_ratio",
            {"sourceUrl": url, "evidenceText": ratio, "rule": "wikipedia.infobox_ratio"},
        )
    if international_ratio:
        field_sources.setdefault("international_student_ratio", url)
        field_evidence.setdefault(
            "international_student_ratio",
            {"sourceUrl": url, "evidenceText": international_ratio, "rule": "wikipedia.infobox_international_ratio"},
        )
    if wiki_contact_person:
        field_sources.setdefault("contact_person", url)
    elif raw_wiki_contact_person:
        field_sources.setdefault("contact_person", url)
    if info.campus and campus_count:
        field_sources.setdefault("university_campuses", url)
        field_evidence.setdefault(
            "university_campuses",
            {"sourceUrl": url, "evidenceText": info.campus, "rule": "wikipedia.infobox_campus_count"},
        )
    if info.campus and life:
        field_sources.setdefault("campus_student_life", url)
        field_evidence.setdefault(
            "campus_student_life",
            {"sourceUrl": url, "evidenceText": info.campus, "rule": "wikipedia.infobox_campus"},
        )
    if financials and financials == parse_financials(labels_text):
        field_sources.setdefault("financials", url)
        field_evidence.setdefault(
            "financials",
            {"sourceUrl": url, "evidenceText": financials, "rule": "wikipedia.infobox_fees"},
        )
    raw_fields = {
        **csv,
        "name": fix_mojibake_text(f"{raw_display_title}, {country['name']}" if country["name"] not in raw_display_title else raw_display_title),
        "description": fix_mojibake_text(raw_description),
        "contact_person": fix_mojibake_text(raw_contact_person),
        "infobox_caption": fix_mojibake_text(info.caption),
        "infobox_type": fix_mojibake_text(info.type),
        "infobox_established": fix_mojibake_text(info.established),
        "infobox_parent_institution": fix_mojibake_text(info.parent_institution),
        "infobox_location": fix_mojibake_text(info.location_text),
        "infobox_campus": fix_mojibake_text(info.campus),
        "infobox_president": fix_mojibake_text(info.president),
        "infobox_principal": fix_mojibake_text(info.principal),
        "official_description": fix_mojibake_text(official["description"]),
    }
    field_warnings: dict[str, list[str]] = {}
    for binary_field in ("sponsored", "student_loan_available", "housing_availability", "immigration_support"):
        if binary_field not in field_evidence:
            add_field_warning(
                field_warnings,
                binary_field,
                "Value defaulted to 0 because no positive source evidence was found; 0 does not mean verified absence.",
            )
            field_evidence[binary_field] = {
                "sourceUrl": url,
                "evidenceText": "0",
                "rule": "defaulted_without_evidence",
            }
            field_sources.setdefault(binary_field, url)
    for header in CSV_HEADERS:
        if not csv.get(header) and raw_fields.get(header):
            add_field_warning(field_warnings, header, "Raw source value exists but export value is blank because it did not satisfy the clean export policy.")
        elif not csv.get(header):
            add_field_warning(field_warnings, header, "No source evidence found for this field.")
    if raw_contact_person and not contact_person:
        add_field_warning(field_warnings, "contact_person", "Contact person source exists but could not be normalized into a usable export value.")
    if raw_description and raw_description != description:
        add_field_warning(field_warnings, "description", "Official raw description was preserved but not used for export because it did not satisfy the English description policy.")
    for failure in official["failures"]:
        add_field_warning(field_warnings, "official", f"Skipped official page ({failure['reason']}): {failure['url']}")
    if official["official_validation"]["status"] in {"rejected", "unreachable"}:
        add_field_warning(
            field_warnings,
            "official",
            official["official_validation"]["reason"],
        )
    for header, source_url in field_sources.items():
        if source_url:
            raw_fields[f"{header}Source"] = source_url
    return {
        **csv,
        "countryName": country["name"],
        "crawlerVersion": CRAWLER_VERSION,
        "countryValidation": validation,
        "officialValidation": official["official_validation"],
        "sourceTitle": fix_mojibake_text(title),
        "candidateWikipediaUrl": candidate_url,
        "wikipediaUrl": url,
        "wikidataId": wikidata_id,
        "officialPages": official["checked"],
        "officialPageFailures": official["failures"],
        "officialStats": official["stats"],
        "academicStats": official["academic_stats"],
        "majorMatches": [
            {"universityName": csv["name"], **item}
            for item in official["major_matches"]
        ],
        "evidence": [
            *([{"type": "wikipedia", "label": "Wikipedia", "url": url}] if not wikidata_id else []),
            *([{"type": "wikidata", "label": "Wikidata", "url": f"https://www.wikidata.org/wiki/{wikidata_id}"}] if wikidata_id else []),
            *([{"type": "official", "label": "Official website", "url": official_url}] if official_url else []),
            *[{"type": "official_page", "label": "Checked official page", "url": item} for item in official["checked"]],
        ],
        "estimatedFields": estimated_fields,
        "rawFields": raw_fields,
        "sourceUrls": {"list": "", "wikipedia": "" if wikidata_id else url, "wikidata": primary_source_url if wikidata_id else "", "official": official_url, **field_sources},
        "fieldSources": {"list": "", "wikipedia": "" if wikidata_id else url, "wikidata": primary_source_url if wikidata_id else "", "official": official_url, **field_sources},
        "fieldEvidence": {
            field: {**details, "checkedAt": now}
            for field, details in field_evidence.items()
        },
        "fieldWarnings": field_warnings,
        "reviewStatus": "Unreviewed",
        "createdAt": now,
        "updatedAt": now,
        "quality": {
            "score": 0,
            "status": "Risky",
            "truthStatus": "Risky",
            "exportReady": False,
            "components": {
                "schemaTypeValidity": 0,
                "fieldCompleteness": 0,
                "sourceEvidenceStrength": 0,
                "websiteContactVerification": 0,
                "consistencyOutliers": 0,
                "duplicateSlugUniqueness": 0,
            },
            "findings": [],
            "riskyFlags": [],
        },
    }


def main() -> int:
    global HTTP_SESSION, REQUESTED_MAJORS, MAJOR_MODE
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--country-code", required=True, type=int)
    parser.add_argument("--country", required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--list-page", default="")
    parser.add_argument("--fetch-mode", choices=["auto", "http", "dynamic", "stealthy"], default="auto")
    parser.add_argument("--request-timeout", type=int, default=8)
    parser.add_argument("--browser-timeout-ms", type=int, default=12000)
    parser.add_argument("--max-official-pages", type=int, default=8)
    parser.add_argument("--max-academic-pages", type=int, default=12)
    parser.add_argument("--max-browser-fallbacks", type=int, default=2)
    parser.add_argument("--skip-guessed-pages-on-failure", action="store_true")
    parser.add_argument("--network-idle", action="store_true")
    parser.add_argument("--disable-resources", action="store_true")
    parser.add_argument("--real-chrome", action="store_true")
    parser.add_argument("--solve-cloudflare", action="store_true")
    parser.add_argument("--majors-json", default="[]")
    parser.add_argument("--major-mode", choices=["discover", "verify"], default="discover")
    parser.add_argument("--base-run-file", default="")
    args = parser.parse_args()
    try:
        parsed_majors = json.loads(args.majors_json)
        REQUESTED_MAJORS = [clean_infobox_value(item) for item in parsed_majors if isinstance(item, str) and clean_infobox_value(item)]
    except json.JSONDecodeError:
        REQUESTED_MAJORS = []
    MAJOR_MODE = args.major_mode
    SCRAPLING_CONFIG.update(
        {
            "fetch_mode": args.fetch_mode,
            "request_timeout": max(3, min(90, args.request_timeout)),
            "browser_timeout_ms": max(5000, min(120000, args.browser_timeout_ms)),
            "max_official_pages": max(0, min(20, args.max_official_pages)),
            "max_academic_pages": max(0, min(50, args.max_academic_pages)),
            "max_browser_fallbacks": max(0, min(10, args.max_browser_fallbacks)),
            "skip_guessed_pages_on_failure": bool(args.skip_guessed_pages_on_failure),
            "network_idle": bool(args.network_idle),
            "disable_resources": bool(args.disable_resources),
            "real_chrome": bool(args.real_chrome),
            "solve_cloudflare": bool(args.solve_cloudflare),
        }
    )
    country = COUNTRIES.get(args.country_code) or {
        "name": args.country,
        "prefix": "+",
        "financials": "USD 3k-25k ($3000-25000)",
        "list_pages": [args.list_page] if args.list_page else [],
        "local": False,
    }
    list_url = args.list_page or country["list_pages"][0]
    emit("started", runId=args.run_id, listPage=list_url)
    features = [
        "Fetcher" if Fetcher is not None else "",
        "FetcherSession" if FetcherSession is not None else "",
        "DynamicFetcher" if DynamicFetcher is not None else "",
        "StealthyFetcher" if StealthyFetcher is not None else "",
        "Selector" if Selector is not None else "",
    ]
    emit(
        "config",
        config={
            "fetchMode": SCRAPLING_CONFIG["fetch_mode"],
            "requestTimeout": SCRAPLING_CONFIG["request_timeout"],
            "browserTimeoutMs": SCRAPLING_CONFIG["browser_timeout_ms"],
            "maxOfficialPages": SCRAPLING_CONFIG["max_official_pages"],
            "maxAcademicPages": SCRAPLING_CONFIG["max_academic_pages"],
            "maxBrowserFallbacks": SCRAPLING_CONFIG["max_browser_fallbacks"],
            "skipGuessedPagesOnFailure": SCRAPLING_CONFIG["skip_guessed_pages_on_failure"],
            "networkIdle": SCRAPLING_CONFIG["network_idle"],
            "disableResources": SCRAPLING_CONFIG["disable_resources"],
            "realChrome": SCRAPLING_CONFIG["real_chrome"],
            "solveCloudflare": SCRAPLING_CONFIG["solve_cloudflare"],
        },
        requestedMajors=REQUESTED_MAJORS,
        majorMode=MAJOR_MODE,
        crawlerVersion=CRAWLER_VERSION,
        features=[feature for feature in features if feature],
    )
    session_context = FetcherSession(impersonate="chrome", retries=1, retry_delay=0) if FetcherSession is not None else None
    try:
        if session_context is not None:
            HTTP_SESSION = session_context.__enter__()
        if args.base_run_file:
            with open(args.base_run_file, "r", encoding="utf-8") as source:
                base_run = json.load(source)
            base_records = list(base_run.get("records") or [])
            emit("discovered", count=len(base_records), listPage=list_url)
            records = []
            errors = []
            for index, record in enumerate(base_records, start=1):
                title = record.get("name") or record.get("sourceTitle") or f"record-{index}"
                emit("progress", current=title, index=index, total=len(base_records), success=len(records), failed=len(errors))
                try:
                    official = inspect_official_site(
                        record.get("website", ""),
                        country,
                        record.get("name") or record.get("sourceTitle") or "",
                    )
                    record["majorMatches"] = [
                        {"universityName": record.get("name", ""), **item}
                        for item in official["major_matches"]
                    ]
                    record["academicStats"] = official["academic_stats"]
                    record["officialPages"] = list(dict.fromkeys([*(record.get("officialPages") or []), *official["checked"]]))
                    record["officialPageFailures"] = official["failures"]
                    record["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    records.append(record)
                    emit(
                        "official_summary",
                        current=title,
                        checked=official["stats"]["checked"],
                        skipped=official["stats"]["skipped"],
                        browserFallbacks=official["stats"]["browserFallbacks"],
                        academic=official["academic_stats"],
                        failures=official["failures"][:3],
                    )
                except Exception as exc:
                    errors.append({"title": title, "error": str(exc)})
                    emit("record_error", current=title, error=str(exc), failed=len(errors))
            emit(
                "final",
                records=records,
                errors=errors,
                rejected=[],
                attemptedCount=len(base_records),
                discoveredCount=len(base_records),
                crawlerVersion=CRAWLER_VERSION,
            )
            return 0
        candidate_limit = min(1000, max(args.limit * 4, args.limit + 100))
        links = discover_links(list_url, candidate_limit)
        emit("discovered", count=len(links), listPage=list_url)
        records = []
        slug_counts: dict[str, int] = {}
        errors = []
        rejected = []
        attempted = 0
        for index, (title, url) in enumerate(links, start=1):
            if len(records) >= args.limit:
                break
            attempted += 1
            emit("progress", current=title, index=index, total=len(links), success=len(records), failed=len(errors))
            try:
                record = build_record(title, url, country, args.country_code, slug_counts)
                record["sourceUrls"]["list"] = list_url
                record["fieldSources"]["list"] = list_url
                records.append(record)
                enriched = [
                    field
                    for field, source_url in (record.get("sourceUrls") or {}).items()
                    if field in CSV_HEADERS and source_url and source_url != record["wikipediaUrl"]
                ]
                if enriched:
                    emit("enriched", current=title, fields=enriched[:12])
                stats = record.get("officialStats") or {}
                failures = record.get("officialPageFailures") or []
                if stats or failures:
                    emit(
                        "official_summary",
                        current=title,
                        checked=stats.get("checked", 0),
                        skipped=stats.get("skipped", 0),
                        browserFallbacks=stats.get("browserFallbacks", 0),
                        academic=record.get("academicStats") or {},
                        failures=failures[:5],
                    )
            except CountryMismatchError as exc:
                rejected.append({"title": title, "url": url, **exc.validation})
                emit("country_rejected", current=title, reason=str(exc), rejected=len(rejected))
            except Exception as exc:  # noqa: BLE001 - progress output should continue.
                errors.append({"title": title, "url": url, "error": str(exc)})
                emit("record_error", current=title, error=str(exc), failed=len(errors))
        emit(
            "final",
            records=records,
            errors=errors,
            rejected=rejected,
            attemptedCount=attempted,
            discoveredCount=len(links),
            crawlerVersion=CRAWLER_VERSION,
        )
    finally:
        if session_context is not None:
            session_context.__exit__(None, None, None)
        HTTP_SESSION = None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
