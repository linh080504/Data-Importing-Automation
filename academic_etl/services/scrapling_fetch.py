"""Scrapling DynamicFetcher wrapper for JS-rendered institution sites.

The default crawler (`crawler.SiteCrawler`) uses requests + BeautifulSoup, which
returns little content for React/Next/Angular university sites that render their
body client-side. Following the Scrapling agent-skill escalation rule ("start
with a static GET; if it returns empty/thin content, escalate to a browser
fetch"), this module renders such pages with Scrapling's ``DynamicFetcher``
(headless Chromium via Playwright).

Design goals:
- **Lazy import**: Scrapling / Playwright browser binaries may not be installed.
  ``dynamic_fetch`` degrades gracefully and returns an ``error`` instead of
  raising, so the crawler always falls back to its requests-based result.
- **Same shape**: returns ``{html, final_url, status_code, error}`` so the
  caller can splice it into its existing result dict.
"""

import logging

logger = logging.getLogger(__name__)

# Cache the import probe so we don't re-import on every page.
_DYNAMIC_FETCHER = None  # None = not probed yet; False = unavailable
_IMPORT_ERROR = ""


def _load_dynamic_fetcher():
    """Return the Scrapling DynamicFetcher class, or False if unavailable."""
    global _DYNAMIC_FETCHER, _IMPORT_ERROR
    if _DYNAMIC_FETCHER is not None:
        return _DYNAMIC_FETCHER
    try:
        from scrapling.fetchers import DynamicFetcher
        _DYNAMIC_FETCHER = DynamicFetcher
    except Exception as exc:  # pragma: no cover - depends on local install
        _DYNAMIC_FETCHER = False
        _IMPORT_ERROR = f"scrapling unavailable: {exc}"
        logger.warning("Scrapling DynamicFetcher unavailable: %s", exc)
    return _DYNAMIC_FETCHER


def dynamic_available() -> bool:
    """True if Scrapling's DynamicFetcher can be imported in this environment."""
    return bool(_load_dynamic_fetcher())


def dynamic_fetch(url: str, *, timeout_ms: int = 30000, network_idle: bool = True,
                  user_agent: str = "", disable_resources: bool = True) -> dict:
    """Render ``url`` with Scrapling's headless DynamicFetcher.

    Returns ``{url, final_url, status_code, html, error}``. On any failure the
    ``error`` key is populated and ``html`` is empty so the caller can fall back
    to its static-fetch result. Never raises.
    """
    result = {"url": url, "final_url": "", "status_code": None, "html": "", "error": ""}
    fetcher = _load_dynamic_fetcher()
    if not fetcher:
        result["error"] = _IMPORT_ERROR or "scrapling unavailable"
        return result

    kwargs = {
        "headless": True,
        "network_idle": network_idle,
        "timeout": timeout_ms,
        # Drop fonts/images/media for speed; we only want rendered HTML/text.
        "disable_resources": disable_resources,
        # Skip ad/tracker domains (Scrapling skill recommendation; saves time).
        "block_ads": True,
    }
    if user_agent:
        kwargs["useragent"] = user_agent

    try:
        page = fetcher.fetch(url, **kwargs)
    except Exception as exc:  # pragma: no cover - browser/runtime dependent
        result["error"] = f"dynamic fetch failed: {str(exc)[:400]}"
        logger.warning("DynamicFetcher failed for %s: %s", url, exc)
        return result

    result["html"] = getattr(page, "html_content", "") or ""
    result["status_code"] = getattr(page, "status", None)
    result["final_url"] = getattr(page, "url", "") or url
    if not result["html"]:
        result["error"] = "dynamic fetch returned empty html"
    return result
