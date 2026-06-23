"""Wikipedia "List of universities in <country>" discovery.

`WikipediaListProvider` resolves a country's English-Wikipedia list article via
the MediaWiki parse API and extracts every linked institution (article title =
English name, plus the article URL). This gives far broader coverage than the
Wikidata `Q38723` query and clean English names. Each institution's article is
later mined for English fields by `services/wikipedia_extract`.

Noise (cities, ministries, "List of …" links, nav/info boxes, references) is
filtered here; whatever slips through is caught downstream by
`classification.classify_institution` (non-higher-ed seeds are never crawled or
imported).
"""

import logging
import re
from urllib.parse import quote

import requests

from .normalize import clean_text

logger = logging.getLogger(__name__)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = ("BeyondDegreeBot/0.1 (academic data pipeline; "
              "contact: linhnguyenthuy0805@gmail.com)")

# Candidate list-article titles, tried in order.
_LIST_TITLE_TEMPLATES = [
    "List of universities in {c}",
    "List of universities and colleges in {c}",
    "List of colleges and universities in {c}",
    "List of higher education institutions in {c}",
    "Higher education in {c}",
]

# Titles that are clearly not a single institution.
_DENY_TITLE_RE = re.compile(
    r"^(list of|lists of|education in|higher education in|ministry|department of|"
    r"national key|outline of|index of|category:|wikipedia:|template:|portal:|"
    r"help:|file:|special:)|"
    r"\(disambiguation\)|university system|education system",
    re.IGNORECASE,
)


def fetch_parse_html(page_title: str, timeout: int = 30) -> tuple[str, str]:
    """Return (resolved_title, html) for a Wikipedia page via the parse API, or
    ("", "") if it doesn't exist. Network boundary — patched in tests."""
    resp = requests.get(
        WIKIPEDIA_API,
        params={"action": "parse", "page": page_title, "prop": "text",
                "format": "json", "redirects": 1},
        headers={"User-Agent": USER_AGENT}, timeout=timeout,
    )
    if resp.status_code != 200:
        return "", ""
    data = resp.json()
    if "error" in data:
        return "", ""
    parse = data.get("parse", {})
    return parse.get("title", ""), parse.get("text", {}).get("*", "")


def article_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))


def _is_institution_title(title: str) -> bool:
    title = (title or "").strip()
    if len(title) < 4 or ":" in title:
        return False
    return not _DENY_TITLE_RE.search(title)


class WikipediaListProvider:
    """Discover institutions for a country from its Wikipedia list article."""

    source_name = "wikipedia"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def discover(self, country_name: str, country_code: str, limit: int = 0) -> list[dict]:
        title, html = self._resolve_list(country_name)
        if not html:
            logger.warning("Wikipedia: no list article found for %s", country_name)
            return []
        seeds = self._parse_institutions(html, country_name, country_code, title)
        logger.info("Wikipedia: %s institutions from '%s'", len(seeds), title)
        return seeds[: limit or None]

    def _resolve_list(self, country_name: str) -> tuple[str, str]:
        for template in _LIST_TITLE_TEMPLATES:
            title, html = fetch_parse_html(template.format(c=country_name), self.timeout)
            if html and "/wiki/" in html:
                return title, html
        return "", ""

    def _parse_institutions(self, html: str, country_name: str,
                            country_code: str, list_title: str) -> list[dict]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        content = soup.find(class_="mw-parser-output") or soup
        # drop boilerplate that holds non-institution links
        for selector in (".navbox", ".infobox", ".reflist", ".hatnote", ".toc",
                         "table.metadata", ".mw-references-wrap", ".mw-editsection",
                         ".thumb", "style", "sup.reference"):
            for tag in content.select(selector):
                tag.decompose()

        source_url = article_url(list_title)
        seen, seeds = set(), []
        # institutions are listed inside tables and bulleted lists
        for a in content.select("table a[href^='/wiki/'], li a[href^='/wiki/']"):
            href = a.get("href", "")
            name = clean_text(a.get("title") or a.get_text())
            if "/wiki/" not in href or not _is_institution_title(name):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            seeds.append({
                "name": name,
                "country": country_name,
                "country_code": country_code,
                "city": "",
                "region": "",
                "website": "",  # filled later from the Wikipedia infobox
                "wikidata_qid": "",
                "wikipedia_url": "https://en.wikipedia.org" + href.split("#")[0],
                "source_name": self.source_name,
                "source_url": source_url,
                "confidence": 0.55,
                "raw_json": {"wikipedia_title": name, "list_article": list_title},
            })
        return seeds
