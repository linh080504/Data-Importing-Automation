"""Polite site crawler: requests + BeautifulSoup.

Guarantees: per-domain rate limit, timeouts, bounded retries, robots.txt
respect (fail-open if robots can't be fetched), depth limit, hard cap on pages
per site, on-disk raw HTML cache keyed by content hash. No infinite crawl.
"""

import hashlib
import logging
import time
import urllib.robotparser
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings

from .scrapling_fetch import dynamic_fetch

logger = logging.getLogger(__name__)

# page_type -> URL/anchor-text keywords (checked lowercase)
PAGE_KEYWORDS = {
    "admissions": ["admission", "apply", "enroll", "entry-requirements"],
    "programs": ["program", "programme", "major", "course", "degree", "undergraduate",
                 "postgraduate", "bachelor", "master", "phd", "doctoral", "academics"],
    "departments": ["department", "faculty", "faculties", "school-of", "schools"],
    "tuition": ["tuition", "fee", "fees", "cost"],
    "scholarships": ["scholarship", "financial-aid", "financial_aid", "bursar"],
    "international": ["international"],
    "campus_life": ["campus-life", "campus_life", "student-life", "student_life",
                    "housing", "accommodation", "hostel"],
    "about": ["about", "overview", "history", "mission"],
    "contact": ["contact", "reach-us", "reach_us"],
    "academics": ["academic"],
}

PRIORITY = ["programs", "departments", "admissions", "academics", "tuition",
            "scholarships", "international", "campus_life", "about", "contact"]

SKIP_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".doc",
                   ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".mp4", ".mp3", ".ico",
                   ".css", ".js", ".webp")

# URL markers for the English version of a multilingual site...
_ENGLISH_PATH_MARKERS = ("/en/", "/en-us", "/en-gb", "/english", "lang=en",
                         "language=en", "setlang=en")
# Default non-English markers; at runtime these are extended with country-specific
# markers via country_registry.get_all_non_english_markers().
_NON_ENGLISH_URL_MARKERS = ("/vi/", "/vi-vn", "/vn/", "/tieng-viet", "lang=vi",
                            "language=vi", "/zh/", "/ja/", "/ko/", "/fr/", "/de/",
                            "/es/", "/ru/", "/th/", "/lo/", "/km/")


def get_with_http_fallback(session, url: str, **kwargs):
    """GET a URL, retrying HTTP only when its HTTPS connection cannot be made.

    Some university sites have a valid HTTP endpoint but broken TLS. Requests
    still follows redirects, and callers persist the final URL, so a working
    HTTPS site is never downgraded.
    """
    try:
        return session.get(url, **kwargs)
    except requests.RequestException as first_error:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            raise
        http_url = parsed._replace(scheme="http").geturl()
        logger.info("HTTPS fetch failed for %s; trying HTTP fallback", url)
        try:
            return session.get(http_url, **kwargs)
        except requests.RequestException as fallback_error:
            raise fallback_error from first_error


def english_home_url(soup, base_url: str) -> str:
    """Return the site's English homepage if it advertises one — via an
    ``hreflang="en"`` alternate or an English language-switcher link — else ""."""
    for link in soup.find_all("link", href=True):
        rels = " ".join(link.get("rel") or []).lower()
        hreflang = (link.get("hreflang") or "").lower()
        if "alternate" in rels and (hreflang == "en" or hreflang.startswith("en-")):
            return urljoin(base_url, link["href"])
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True).lower()
        low = a["href"].strip().lower()
        if text in ("english", "en", "eng") or "english" in text:
            return urljoin(base_url, a["href"])
        if low.rstrip("/").endswith("/en") or any(m in low for m in _ENGLISH_PATH_MARKERS):
            return urljoin(base_url, a["href"])
    return ""


def _is_non_english_url(url: str, country_code: str = "") -> bool:
    low = url.lower()
    if country_code:
        from .country_registry import get_all_non_english_markers
        markers = get_all_non_english_markers(country_code)
    else:
        markers = _NON_ENGLISH_URL_MARKERS
    return any(marker in low for marker in markers)


def classify_link(url: str, anchor_text: str = "") -> str:
    haystack = f"{url} {anchor_text}".lower()
    for page_type in PRIORITY:
        if any(kw in haystack for kw in PAGE_KEYWORDS[page_type]):
            return page_type
    return "other"


class SiteCrawler:
    def __init__(self, user_agent=None, timeout=None, rate_limit=None,
                 max_pages=None, max_depth=None, cache_dir=None,
                 use_dynamic_fallback=None, dynamic_min_text_chars=None,
                 dynamic_timeout_ms=None, dynamic_network_idle=None,
                 country_code=None):
        self.country_code = country_code or ""
        self.user_agent = user_agent or settings.ETL_USER_AGENT
        self.timeout = timeout or settings.ETL_REQUEST_TIMEOUT
        self.rate_limit = rate_limit if rate_limit is not None else settings.ETL_RATE_LIMIT_SECONDS
        self.max_pages = max_pages or settings.ETL_MAX_PAGES_PER_SITE
        self.max_depth = max_depth if max_depth is not None else settings.ETL_MAX_CRAWL_DEPTH
        self.cache_dir = cache_dir or settings.ETL_HTML_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Scrapling DynamicFetcher fallback for JS-rendered sites (off by default).
        self.use_dynamic_fallback = (
            use_dynamic_fallback if use_dynamic_fallback is not None
            else getattr(settings, "ETL_USE_DYNAMIC_FALLBACK", False)
        )
        self.dynamic_min_text_chars = (
            dynamic_min_text_chars if dynamic_min_text_chars is not None
            else getattr(settings, "ETL_DYNAMIC_MIN_TEXT_CHARS", 500)
        )
        self.dynamic_timeout_ms = (
            dynamic_timeout_ms if dynamic_timeout_ms is not None
            else getattr(settings, "ETL_DYNAMIC_TIMEOUT_MS", 30000)
        )
        self.dynamic_network_idle = (
            dynamic_network_idle if dynamic_network_idle is not None
            else getattr(settings, "ETL_DYNAMIC_NETWORK_IDLE", True)
        )
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.user_agent
        self._last_request_at = {}
        self._robots = {}

    # ---- politeness -------------------------------------------------------

    def _respect_rate_limit(self, host: str):
        last = self._last_request_at.get(host)
        if last is not None:
            wait = self.rate_limit - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request_at[host] = time.monotonic()

    def _robots_allows(self, url: str) -> bool:
        host = urlparse(url).netloc
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
            try:
                rp.set_url(robots_url)
                rp.read()
                self._robots[host] = rp
            except Exception:  # robots unavailable -> fail open
                self._robots[host] = None
        rp = self._robots[host]
        if rp is None:
            return True
        try:
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True

    # ---- fetching ---------------------------------------------------------

    def fetch(self, url: str, retries: int = 2) -> dict:
        """Fetch one URL. Returns {url, final_url, status_code, html, error,
        html_hash, cache_path, fetch_method}.

        Strategy (Scrapling agent-skill escalation rule): try a static requests
        GET first; if it succeeds but the rendered text is JS-thin and the
        dynamic fallback is enabled, re-render with Scrapling's DynamicFetcher
        and keep whichever HTML has more visible text.
        """
        result = {"url": url, "final_url": "", "status_code": None, "html": "",
                  "error": "", "html_hash": "", "cache_path": "", "fetch_method": "requests"}
        if not self._robots_allows(url):
            result["error"] = "blocked by robots.txt"
            return result
        host = urlparse(url).netloc
        for attempt in range(retries + 1):
            self._respect_rate_limit(host)
            try:
                resp = get_with_http_fallback(
                    self.session, url, timeout=self.timeout, allow_redirects=True,
                )
                result["status_code"] = resp.status_code
                result["final_url"] = resp.url
                if resp.status_code >= 500 and attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                ctype = resp.headers.get("Content-Type", "")
                if "html" not in ctype and "<html" not in resp.text[:1000].lower():
                    result["error"] = f"non-HTML content-type: {ctype}"
                    return result
                html = resp.text
                if self.use_dynamic_fallback and self._looks_thin(html):
                    html = self._try_dynamic(url, html, result)
                self._store_html(result, html)
                return result
            except requests.RequestException as exc:
                result["error"] = str(exc)[:500]
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
        return result

    # ---- JS-thin detection + dynamic fallback -----------------------------

    @staticmethod
    def _visible_text_len(html: str) -> int:
        """Length of human-visible text (scripts/styles stripped)."""
        if not html:
            return 0
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        return len(soup.get_text(" ", strip=True))

    def _looks_thin(self, html: str) -> bool:
        """True if the page renders too little text to extract from (likely a
        client-side-rendered SPA shell)."""
        return self._visible_text_len(html) < self.dynamic_min_text_chars

    def _try_dynamic(self, url: str, static_html: str, result: dict) -> str:
        """Re-render ``url`` with Scrapling. Returns whichever HTML has more
        visible text and records the method used on ``result``."""
        dyn = dynamic_fetch(
            url,
            timeout_ms=self.dynamic_timeout_ms,
            network_idle=self.dynamic_network_idle,
            user_agent=self.user_agent,
        )
        if dyn.get("error") or not dyn.get("html"):
            logger.info("dynamic fallback unused for %s: %s", url, dyn.get("error"))
            return static_html
        if self._visible_text_len(dyn["html"]) <= self._visible_text_len(static_html):
            logger.info("dynamic fallback no richer than static for %s", url)
            return static_html
        logger.info("dynamic fallback used for %s (JS-rendered)", url)
        result["fetch_method"] = "scrapling_dynamic"
        if dyn.get("final_url"):
            result["final_url"] = dyn["final_url"]
        if dyn.get("status_code") is not None:
            result["status_code"] = dyn["status_code"]
        return dyn["html"]

    def _store_html(self, result: dict, html: str):
        """Attach html to result and cache it on disk keyed by content hash."""
        result["html"] = html
        digest = hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()
        result["html_hash"] = digest
        cache_path = self.cache_dir / f"{digest}.html"
        if not cache_path.exists():
            cache_path.write_text(html, encoding="utf-8", errors="replace")
        result["cache_path"] = str(cache_path)

    # ---- site crawl -------------------------------------------------------

    def crawl_site(self, start_url: str) -> list[dict]:
        """BFS crawl of one institution site. Returns fetched page dicts with
        keys: url, final_url, status_code, html, error, html_hash, cache_path,
        page_type, depth, title, soup.

        When `ETL_PREFER_ENGLISH` is on and the homepage advertises an English
        version (hreflang=en or a language-switcher link), the crawl switches to
        that English root and stops following other-language pages — so a global
        catalog is built in English without machine translation."""
        prefer_english = getattr(settings, "ETL_PREFER_ENGLISH", True)
        allowed_hosts = {urlparse(start_url).netloc.lower().removeprefix("www.")}
        english_mode = False
        seen, pages = set(), []
        # queue of (url, depth, page_type_hint); homepage first
        queue = [(start_url, 0, "homepage")]

        while queue and len(pages) < self.max_pages:
            # prefer interesting pages: stable sort by priority of hint
            queue.sort(key=lambda item: (item[1], _type_rank(item[2])))
            url, depth, hint = queue.pop(0)
            norm = urldefrag(url)[0].rstrip("/")
            if norm in seen:
                continue
            seen.add(norm)

            page = self.fetch(url)
            page.update({"depth": depth, "page_type": hint, "title": "", "soup": None})
            if page["html"]:
                soup = BeautifulSoup(page["html"], "html.parser")
                page["soup"] = soup
                title_tag = soup.find("title")
                page["title"] = title_tag.get_text(strip=True)[:500] if title_tag else ""
                base = page["final_url"] or url
                # On the homepage, hop to the English version if one exists.
                if hint == "homepage" and prefer_english and not english_mode:
                    en_url = english_home_url(soup, base)
                    if en_url and urldefrag(en_url)[0].rstrip("/") != norm:
                        english_mode = True
                        allowed_hosts.add(urlparse(en_url).netloc.lower().removeprefix("www."))
                        queue.insert(0, (en_url, 0, "homepage"))
                        logger.info("switching to English version: %s", en_url)
                if depth < self.max_depth:
                    for link_url, link_type in self._extract_links(
                            soup, base, allowed_hosts, drop_non_english=english_mode):
                        link_norm = urldefrag(link_url)[0].rstrip("/")
                        if link_norm not in seen:
                            queue.append((link_url, depth + 1, link_type))
            pages.append(page)
            logger.info("crawled [%s] depth=%s status=%s %s",
                        page["page_type"], depth, page["status_code"], url)
        return pages

    def _extract_links(self, soup, base_url: str, allowed_hosts, drop_non_english: bool = False):
        if isinstance(allowed_hosts, str):  # back-compat: single host
            allowed_hosts = {allowed_hosts}
        found = {}
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in ("http", "https"):
                continue
            host = parsed.netloc.lower().removeprefix("www.")
            if host not in allowed_hosts:
                continue
            if parsed.path.lower().endswith(SKIP_EXTENSIONS):
                continue
            if drop_non_english and _is_non_english_url(absolute, self.country_code):
                continue  # other-language duplicate of an English page
            page_type = classify_link(absolute, a.get_text(" ", strip=True))
            if page_type == "other":
                continue  # only follow links we recognize as relevant
            found.setdefault(urldefrag(absolute)[0], page_type)
        return list(found.items())


def _type_rank(page_type: str) -> int:
    if page_type == "homepage":
        return -1
    try:
        return PRIORITY.index(page_type)
    except ValueError:
        return len(PRIORITY)
