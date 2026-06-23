"""Cross-source reconciliation for knowledge-base-seeded institutions.

When a seed comes from Wikidata/Wikipedia (`InstitutionSeed.source_name`), the
seed itself asserts a few facts (name, official website, city/region). After the
official website is crawled, we want to:

1. Record those KB-asserted values as `FieldEvidence` so the review UI can show
   them side-by-side with what the official website actually says.
2. Keep the KB evidence at a LOWER confidence than official-website evidence, so
   the official site always ranks first (and wins on import).
3. Detect conflicts (KB value disagrees with the official site) and report the
   fields so validation can force the record to `needs_review`.

Pure-ish helpers here; persistence is done by the caller (`pipeline.crawl_seed`).
"""

from academic_etl.models import FieldEvidence

from .normalize import normalize_program_name, url_domain

# Knowledge-base sources and the confidence their asserted values get. These sit
# BELOW the official-website extractor confidences (name >= 0.6, website 0.9).
SOURCE_CONFIDENCE = {"wikidata": 0.5}
KB_SOURCES = set(SOURCE_CONFIDENCE)

# Confidence for "the official homepage resolved to this domain" evidence.
OFFICIAL_WEBSITE_CONFIDENCE = 0.9


def seed_source_values(seed) -> dict:
    """The fields a KB seed asserts, for cross-checking against the crawl."""
    values = {}
    if seed.name:
        values["name"] = seed.name.strip()
    if seed.website:
        values["website"] = seed.website.strip()
    location = (seed.city or seed.region or "").strip()
    if location:
        values["location"] = location
    return values


def homepage_domain(pages: list[dict]) -> str:
    """Domain of the crawled official homepage (empty if none fetched)."""
    for page in pages:
        if page.get("page_type") == "homepage" and page.get("html"):
            return url_domain(page.get("final_url") or page.get("url", ""))
    return ""


def homepage_url(pages: list[dict]) -> str:
    for page in pages:
        if page.get("page_type") == "homepage" and page.get("html"):
            return page.get("final_url") or page.get("url", "")
    return ""


def _names_conflict(a: str, b: str) -> bool:
    na, nb = normalize_program_name(a), normalize_program_name(b)
    if not na or not nb:
        return False
    # No conflict if one name contains the other (handles "MIT" vs
    # "Massachusetts Institute of Technology | Home" style differences).
    return not (na == nb or na in nb or nb in na)


def detect_conflicts(seed, extracted: dict, pages: list[dict]) -> list[str]:
    """Fields where the KB seed and the official website disagree."""
    conflicts = []
    official_name = (extracted.get("name") or {}).get("value", "")
    if seed.name and official_name and _names_conflict(seed.name, official_name):
        conflicts.append("name")

    seed_domain = url_domain(seed.website)
    off_domain = homepage_domain(pages)
    if seed_domain and off_domain and seed_domain != off_domain:
        conflicts.append("website")
    return conflicts


def build_source_evidence(uni, seed, now) -> list[FieldEvidence]:
    """KB-asserted values as low-confidence FieldEvidence rows."""
    confidence = SOURCE_CONFIDENCE.get(seed.source_name, 0.4)
    source_url = seed.wikipedia_url or seed.source_url
    rows = []
    for field, value in seed_source_values(seed).items():
        rows.append(FieldEvidence(
            entity_type="university", entity_id=uni.pk, field_name=field,
            extracted_value=str(value)[:5000], normalized_value=str(value)[:5000],
            source_url=(source_url or "")[:1000],
            page_title="Wikidata / Wikipedia", page_type="wikidata", css_selector="",
            text_snippet=f"{seed.source_name}: {value}"[:500],
            confidence_score=confidence, extractor_name=seed.source_name,
            extraction_method="wikidata", crawled_at=now, raw_html_hash="",
        ))
    return rows


def build_official_website_evidence(uni, pages, now) -> list[FieldEvidence]:
    """High-confidence evidence that the official homepage resolves — so the
    `website` field ranks the official site above the KB-asserted URL."""
    url = homepage_url(pages)
    if not url:
        return []
    return [FieldEvidence(
        entity_type="university", entity_id=uni.pk, field_name="website",
        extracted_value=url[:5000], normalized_value=url[:5000],
        source_url=url[:1000], page_title="Official homepage", page_type="homepage",
        css_selector="", text_snippet=f"Official site reachable: {url}"[:500],
        confidence_score=OFFICIAL_WEBSITE_CONFIDENCE, extractor_name="homepage_resolve",
        extraction_method="rule", crawled_at=now, raw_html_hash="",
    )]
