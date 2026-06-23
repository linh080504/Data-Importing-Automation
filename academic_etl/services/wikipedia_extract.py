"""Extract English university fields from a Wikipedia article.

`extract_wikipedia_university(url)` fetches the article via the MediaWiki parse
API and reads the infobox (website, students, location→city, type) plus the lead
paragraph (description). The values are English by construction, so this is the
common-language backbone the official-site crawl later enriches. Returns
``{field: evidence-dict}`` in the same shape as `extraction._evidence`.

`extract_programs_from_wikipedia(url)` fetches the Departments/Academics section
and parses the bullet list of departments/programs.
"""

import logging
import re
from urllib.parse import unquote

import requests

from .normalize import clean_text, normalize_int, normalize_url
from .wikipedia import fetch_parse_html, WIKIPEDIA_API, USER_AGENT

logger = logging.getLogger(__name__)


def _title_from_url(url: str) -> str:
    seg = url.rstrip("/").split("/wiki/")[-1].split("#")[0]
    return unquote(seg).replace("_", " ")


def _evidence(value, source_url, snippet, confidence, extractor):
    return {
        "value": value, "source_url": source_url, "page_title": "Wikipedia",
        "page_type": "wikipedia", "css_selector": "table.infobox",
        "text_snippet": clean_text(snippet)[:500], "confidence": confidence,
        "extractor": extractor, "raw_html_hash": "",
    }


def _find_label(labels: dict, keywords: list[str]):
    for label, td in labels.items():
        if any(kw in label for kw in keywords):
            return td
    return None


def _strip_parentheticals(text: str) -> str:
    """Drop all '( … )' groups (incl. nested) — Wikipedia leads put native-
    language names / abbreviations there."""
    out, depth = [], 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return clean_text("".join(out))


def _city_from_location(location: str, country: str = "") -> str:
    """Best-effort English city from an infobox Location ('addr, City, Country …').
    Drops coordinate/number chunks and a trailing country name."""
    location = location.replace("﻿", "").replace("​", "")
    parts = [p.strip() for p in re.split(r"[,/\n]", location) if p.strip()]
    # keep place-like parts (have letters, no digits/coordinate marks)
    places = [p for p in parts if re.search(r"[A-Za-zÀ-ỹ]", p)
              and not re.search(r"[0-9°′″]", p)]
    if not places:
        return ""
    if country and len(places) >= 2 and places[-1].lower() == country.lower():
        return places[-2][:120]
    return places[-1][:120]


def extract_wikipedia_university(wikipedia_url: str, country: str = "", html: str | None = None) -> dict:
    """Return {field: evidence-dict} from a Wikipedia article. If ``html`` is
    given (e.g. concurrently prefetched) it's used directly; otherwise the
    article is fetched here."""
    if html is None:
        _, html = fetch_parse_html(_title_from_url(wikipedia_url))
    if not html:
        return {}
    return parse_university_html(html, wikipedia_url, country)


def parse_university_html(html: str, wikipedia_url: str, country: str = "") -> dict:
    """Pure parse of a Wikipedia article's HTML into {field: evidence-dict}."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    fields = {}

    box = soup.find("table", class_="infobox")
    labels = {}
    if box:
        for tr in box.find_all("tr"):
            th, td = tr.find("th"), tr.find("td")
            if th and td:
                labels[clean_text(th.get_text(" ")).lower()] = td

    td = _find_label(labels, ["website"])
    if td is not None:
        a = td.find("a", href=True)
        raw = a["href"] if a else clean_text(td.get_text(" "))
        url = normalize_url(raw)
        if url:
            fields["website"] = _evidence(url, wikipedia_url, raw, 0.75, "wikipedia_infobox")

    td = _find_label(labels, ["students", "enrollment", "undergraduates"])
    if td is not None:
        n = normalize_int(td.get_text(" "))
        if n:
            fields["number_of_students"] = _evidence(
                n, wikipedia_url, td.get_text(" ")[:120], 0.7, "wikipedia_infobox")

    td = _find_label(labels, ["location", "city"])
    if td is not None:
        city = _city_from_location(td.get_text(", ", strip=True), country)
        if city:
            fields["city"] = _evidence(city, wikipedia_url, td.get_text(" ")[:120],
                                       0.6, "wikipedia_infobox")

    content = soup.find(class_="mw-parser-output")
    if content is not None:
        for p in content.find_all("p", recursive=False):
            text = clean_text(p.get_text(" "))
            if len(text) > 80:
                fields["description"] = _evidence(
                    _strip_parentheticals(text)[:2000], wikipedia_url, text[:200],
                    0.65, "wikipedia_lead")
                break
    return fields


# ---------------------------------------------------------------------------
# Program/department extraction from Wikipedia article sections
# ---------------------------------------------------------------------------

_ACADEMIC_SECTION_KEYWORDS = [
    "department", "academic department", "facult", "school",
    "programme", "program", "academics", "divisions",
]

_NOISE_PREFIXES = re.compile(
    r"^(centre for|center for|national centre|centre of|"
    r"sophisticated|tata centre|koita|wadhwani|parimal|"
    r"\^|see also|references|external|note)",
    re.IGNORECASE,
)


def extract_programs_from_wikipedia(wikipedia_url: str) -> list[dict]:
    """Extract departments/programs from Wikipedia article's academic sections.

    Uses MediaWiki API to:
    1. List all sections → find "Departments", "Academics", etc.
    2. Fetch that section's HTML
    3. Parse <li> items as department/program names

    Returns list of dicts: [{program_name, faculty_or_school}, ...]
    """
    title = _title_from_url(wikipedia_url)
    if not title:
        return []

    # Step 1: Get sections list
    try:
        resp = requests.get(WIKIPEDIA_API, params={
            "action": "parse", "page": title, "prop": "sections",
            "format": "json", "redirects": 1,
        }, headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if "error" in data:
            return []
        sections = data.get("parse", {}).get("sections", [])
    except Exception:
        return []

    # Step 2: Find academic sections
    target_sections = []
    for sec in sections:
        name = sec.get("line", "").lower()
        if any(kw in name for kw in _ACADEMIC_SECTION_KEYWORDS):
            target_sections.append(sec)

    if not target_sections:
        return []

    # Step 3: Fetch and parse each relevant section
    programs = []
    seen = set()
    parent_school = ""

    for sec in target_sections:
        section_name = sec.get("line", "")
        level = int(sec.get("level", 2))

        # Use section name as faculty_or_school context
        if level <= 3:
            parent_school = section_name

        try:
            resp = requests.get(WIKIPEDIA_API, params={
                "action": "parse", "page": title, "prop": "text",
                "section": sec["index"], "format": "json", "redirects": 1,
            }, headers={"User-Agent": USER_AGENT}, timeout=10)
            if resp.status_code != 200:
                continue
            html = resp.json().get("parse", {}).get("text", {}).get("*", "")
            if not html:
                continue
        except Exception:
            continue

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Remove reference/footnote elements
        for tag in soup.select("sup.reference, .reflist, .mw-editsection"):
            tag.decompose()

        for li in soup.find_all("li"):
            text = clean_text(li.get_text(" "))
            if not text or len(text) < 4 or len(text) > 120:
                continue
            if _NOISE_PREFIXES.search(text):
                continue

            key = text.lower().strip()
            if key in seen:
                continue
            seen.add(key)

            # Extract link URL if available
            link = li.find("a", href=True)
            prog_url = ""
            if link and "/wiki/" in link.get("href", ""):
                prog_url = "https://en.wikipedia.org" + link["href"].split("#")[0]

            programs.append({
                "program_name": text[:200],
                "faculty_or_school": parent_school,
                "source": "wikipedia_section",
                "program_url": prog_url,
            })

    logger.info("Wikipedia programs for %s: %d departments/programs from %d sections",
                title, len(programs), len(target_sections))
    return programs
