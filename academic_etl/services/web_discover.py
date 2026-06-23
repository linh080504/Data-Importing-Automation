"""Additional university discovery by scraping public listing pages.

Supplements Wikipedia + Wikidata with data from:
- UniRank/4icu.org (comprehensive global listings)
- Country-specific education portal pages

Returns seed dicts in the same format as the other discovery providers.
"""

import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .normalize import clean_text, normalize_url

logger = logging.getLogger(__name__)

USER_AGENT = ("BeyondDegreeBot/0.1 (academic data pipeline; "
              "contact: linhnguyenthuy0805@gmail.com)")

_COUNTRY_UNIRANK_SLUGS = {
    "IN": "india", "VN": "vietnam", "US": "united-states", "GB": "united-kingdom",
    "AU": "australia", "CA": "canada", "DE": "germany", "FR": "france",
    "JP": "japan", "CN": "china", "SG": "singapore", "KR": "south-korea",
    "MY": "malaysia", "TH": "thailand", "ID": "indonesia", "PH": "philippines",
    "NL": "netherlands", "BR": "brazil", "MX": "mexico", "EG": "egypt",
    "SA": "saudi-arabia", "AE": "united-arab-emirates", "NG": "nigeria",
    "KE": "kenya", "ZA": "south-africa", "ES": "spain", "IT": "italy",
    "RU": "russia", "TR": "turkey", "PK": "pakistan", "BD": "bangladesh",
}

_INSTITUTION_KEYWORDS = re.compile(
    r"universit|institut|college|polytechnic|academy|school of|"
    r"大学|학교|विश्वविद्यालय|université|universität|جامعة",
    re.IGNORECASE,
)


def discover_from_web(country_name: str, country_code: str, limit: int = 0) -> list[dict]:
    """Discover universities from web listings (UniRank + generic search).

    Returns list of seed dicts compatible with run_discovery().
    """
    seeds = []
    seen_names = set()

    # Source 1: UniRank (4icu.org) — comprehensive global university database
    unirank_seeds = _discover_unirank(country_name, country_code)
    for s in unirank_seeds:
        key = s["name"].strip().lower()
        if key not in seen_names:
            seeds.append(s)
            seen_names.add(key)

    # Source 2: Wikipedia subcategory pages (catch institutions not on the main list)
    subcat_seeds = _discover_wikipedia_subcategories(country_name, country_code)
    for s in subcat_seeds:
        key = s["name"].strip().lower()
        if key not in seen_names:
            seeds.append(s)
            seen_names.add(key)

    logger.info("Web discovery for %s: %d institutions from UniRank + subcategories", country_name, len(seeds))
    return seeds[:limit] if limit else seeds


def _discover_unirank(country_name: str, country_code: str) -> list[dict]:
    """Scrape university listings from 4icu.org/reviews (public, no auth needed)."""
    slug = _COUNTRY_UNIRANK_SLUGS.get(country_code.upper(), country_name.lower().replace(" ", "-"))
    url = f"https://www.4icu.org/reviews/{slug}/"
    seeds = []

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        if resp.status_code != 200:
            logger.debug("UniRank returned %d for %s", resp.status_code, url)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        for row in soup.select("table tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            link = cells[1].find("a") if len(cells) > 1 else cells[0].find("a")
            if not link:
                continue
            name = clean_text(link.get_text())
            if not name or len(name) < 4:
                continue
            if not _INSTITUTION_KEYWORDS.search(name):
                continue

            href = link.get("href", "")
            detail_url = urljoin(url, href) if href else ""

            seeds.append({
                "name": name,
                "country": country_name,
                "country_code": country_code,
                "city": "",
                "region": "",
                "website": "",
                "wikidata_qid": "",
                "wikipedia_url": "",
                "source_name": "unirank",
                "source_url": detail_url or url,
                "confidence": 0.50,
                "raw_json": {"source": "unirank", "detail_url": detail_url},
            })
    except Exception as exc:
        logger.warning("UniRank scrape failed for %s: %s", country_name, exc)

    return seeds


def _discover_wikipedia_subcategories(country_name: str, country_code: str) -> list[dict]:
    """Discover institutions from Wikipedia category pages (broader than list articles).

    Searches "Category:Universities in <country>" which includes subcategories
    like "Category:Universities in <state>" that the main list article may miss.
    """
    api_url = "https://en.wikipedia.org/w/api.php"
    category = f"Category:Universities in {country_name}"
    seeds = []

    try:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmtype": "page|subcat",
            "cmlimit": "500",
            "format": "json",
        }
        resp = requests.get(api_url, params=params,
                           headers={"User-Agent": USER_AGENT}, timeout=20)
        if resp.status_code != 200:
            return []
        data = resp.json()
        members = data.get("query", {}).get("categorymembers", [])

        for member in members:
            title = member.get("title", "")
            ns = member.get("ns", 0)

            if ns == 14:  # Subcategory — recurse one level
                sub_seeds = _fetch_category_members(api_url, title, country_name, country_code)
                seeds.extend(sub_seeds)
            elif ns == 0:  # Article page
                if _INSTITUTION_KEYWORDS.search(title):
                    seeds.append(_make_wikipedia_seed(title, country_name, country_code))

    except Exception as exc:
        logger.warning("Wikipedia category discovery failed for %s: %s", country_name, exc)

    return seeds


def _fetch_category_members(api_url: str, category: str,
                            country_name: str, country_code: str) -> list[dict]:
    """Fetch article members of a Wikipedia subcategory (one level only)."""
    seeds = []
    try:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmtype": "page",
            "cmlimit": "500",
            "format": "json",
        }
        resp = requests.get(api_url, params=params,
                           headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        for member in data.get("query", {}).get("categorymembers", []):
            title = member.get("title", "")
            if title and _INSTITUTION_KEYWORDS.search(title):
                seeds.append(_make_wikipedia_seed(title, country_name, country_code))
    except Exception:
        pass
    return seeds


def _make_wikipedia_seed(title: str, country_name: str, country_code: str) -> dict:
    """Create a seed dict from a Wikipedia article title."""
    from urllib.parse import quote
    return {
        "name": title,
        "country": country_name,
        "country_code": country_code,
        "city": "",
        "region": "",
        "website": "",
        "wikidata_qid": "",
        "wikipedia_url": "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_")),
        "source_name": "wikipedia_category",
        "source_url": "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_")),
        "confidence": 0.50,
        "raw_json": {"wikipedia_title": title, "source": "category"},
    }
