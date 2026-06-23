"""Concurrent fetching for the catalog builder.

Fetching hundreds of Wikipedia articles one-by-one is the slow part of a country
run. `fetch_articles_html` parallelizes just the network step with a bounded
thread pool (each call is a stateless `requests` GET to the MediaWiki API, so
threads are safe). Parsing and all DB writes stay on the main thread afterwards,
which keeps SQLite happy (no concurrent writers).
"""

import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


def fetch_articles_html(urls: list[str], max_workers: int = 6,
                        timeout: int = 30) -> dict[str, str]:
    """Return {wikipedia_url: html} fetched concurrently. Failed fetches map to
    an empty string so the caller can fall back to a sequential fetch."""
    from .wikipedia import fetch_parse_html
    from .wikipedia_extract import _title_from_url

    unique = list(dict.fromkeys(u for u in urls if u))
    if not unique:
        return {}

    def _one(url: str) -> tuple[str, str]:
        try:
            _, html = fetch_parse_html(_title_from_url(url), timeout)
            return url, html
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("article fetch failed %s: %s", url, exc)
            return url, ""

    workers = max(1, min(max_workers, len(unique)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(pool.map(_one, unique))
    got = sum(1 for v in results.values() if v)
    logger.info("fetched %s/%s Wikipedia articles (%s workers)", got, len(unique), workers)
    return results
