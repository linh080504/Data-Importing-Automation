"""Multi-source web scraper for university data.

Scrapes structured data from public web sources that aggregate university info:
1. Wikipedia infobox (expanded: all fields including campus, type, established)
2. QS Top Universities (ranking, students, faculty ratio, international %)
3. 4icu.org / UniRank (comprehensive listings with links)
4. University's own website (contact, admissions, financials)

The key insight: ranking sites and Wikipedia have ALREADY parsed and structured
university data. Scraping them is free, fast, and more accurate than trying to
parse each university's unique HTML layout.

Each source returns a dict of {field: {value, source_url, confidence}}.
The reconciler picks the highest-confidence value for each field.
"""

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from .crawler import get_with_http_fallback
from .normalize import PHONE_RE, clean_text, normalize_int, normalize_phone, normalize_url

logger = logging.getLogger(__name__)

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}

ALL_FIELDS = [
    "name", "location", "description", "website", "global_rank", "financials",
    "campus_student_life", "number_of_students", "student_to_faculty_ratio",
    "international_student_ratio", "housing_availability", "admissions_contact",
    "admissions_phone", "contact_person", "admissions_page_link",
    "immigration_support", "university_campuses", "student_loan_available",
]


def scrape_university_multi_source(
    name: str, country: str, country_code: str = "",
    website: str = "", wikipedia_url: str = "",
) -> dict:
    """Scrape data for one university from all available web sources.

    Returns {field_name: {"value": ..., "source": ..., "confidence": ...}}
    with the best value per field chosen by confidence score.
    """
    all_evidence = {}

    # Source 1: Wikipedia (expanded infobox + lead)
    if wikipedia_url:
        try:
            wiki_data = _scrape_wikipedia_expanded(wikipedia_url)
            _merge(all_evidence, wiki_data)
        except Exception as exc:
            logger.debug("Wikipedia scrape failed for %s: %s", name, exc)

    # Source 2: QS Top Universities search
    try:
        qs_data = _scrape_qs_ranking(name, country)
        _merge(all_evidence, qs_data)
    except Exception as exc:
        logger.debug("QS scrape failed for %s: %s", name, exc)

    # Source 3: University's own website (contact page, about page)
    if website:
        try:
            site_data = _scrape_official_site(website, name)
            _merge(all_evidence, site_data)
        except Exception as exc:
            logger.debug("Official site scrape failed for %s: %s", name, exc)

    # Convert to simple {field: value} dict
    result = {}
    for field, evidence in all_evidence.items():
        result[field] = evidence["value"]

    return result


def _merge(target: dict, source: dict):
    """Merge source into target, keeping higher confidence values."""
    for field, evidence in source.items():
        if field not in target or evidence["confidence"] > target[field]["confidence"]:
            target[field] = evidence


# ---------------------------------------------------------------------------
# Source 1: Wikipedia (expanded)
# ---------------------------------------------------------------------------

def _scrape_wikipedia_expanded(wikipedia_url: str) -> dict:
    """Extract ALL available fields from Wikipedia infobox + article body."""
    from .wikipedia import fetch_parse_html

    title = wikipedia_url.rstrip("/").split("/wiki/")[-1].replace("_", " ")
    from urllib.parse import unquote
    title = unquote(title)
    _, html = fetch_parse_html(title)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    fields = {}

    # Parse infobox
    box = soup.find("table", class_="infobox")
    labels = {}
    if box:
        for tr in box.find_all("tr"):
            th, td = tr.find("th"), tr.find("td")
            if th and td:
                labels[clean_text(th.get_text(" ")).lower()] = td

    def _get(keywords, field, confidence=0.7):
        for label, td in labels.items():
            if any(kw in label for kw in keywords):
                val = clean_text(td.get_text(" "))
                if val:
                    fields[field] = {"value": val, "source": wikipedia_url, "confidence": confidence}
                    return val
        return None

    _get(["website", "url"], "website", 0.75)
    # Fix website to actual URL
    if "website" in fields:
        a = None
        for label, td in labels.items():
            if "website" in label or "url" in label:
                a = td.find("a", href=True)
                break
        if a:
            url = normalize_url(a["href"])
            if url:
                fields["website"]["value"] = url

    val = _get(["students", "enrollment", "undergraduates"], "number_of_students", 0.7)
    if val:
        n = normalize_int(val)
        if n:
            fields["number_of_students"]["value"] = n

    _get(["location", "address", "city"], "location", 0.65)
    _get(["type"], "_type", 0.6)
    _get(["campus"], "campus_student_life", 0.55)
    _get(["established", "founded"], "_established", 0.6)
    _get(["academic staff", "faculty"], "_academic_staff", 0.6)
    _get(["motto"], "_motto", 0.5)
    _get(["endowment"], "_endowment", 0.5)

    # Calculate student-to-faculty ratio from students / academic_staff
    if "number_of_students" in fields and "_academic_staff" in fields:
        try:
            students = int(fields["number_of_students"]["value"])
            staff_text = fields["_academic_staff"]["value"]
            staff = normalize_int(staff_text)
            if staff and staff > 0:
                ratio = round(students / staff)
                fields["student_to_faculty_ratio"] = {
                    "value": str(ratio), "source": wikipedia_url, "confidence": 0.6,
                }
        except (ValueError, TypeError):
            pass

    # Build description from established + type + lead paragraph
    description_parts = []
    content = soup.find(class_="mw-parser-output")
    if content:
        for p in content.find_all("p", recursive=False):
            text = clean_text(p.get_text(" "))
            if len(text) > 80:
                # Strip parenthetical foreign names
                text = re.sub(r"\([^)]*\)", "", text).strip()
                text = re.sub(r"\s+", " ", text)
                description_parts.append(text[:500])
                break

    if description_parts:
        fields["description"] = {
            "value": description_parts[0], "source": wikipedia_url, "confidence": 0.65,
        }

    # Remove internal fields
    fields.pop("_type", None)
    fields.pop("_established", None)
    fields.pop("_academic_staff", None)
    fields.pop("_motto", None)
    fields.pop("_endowment", None)

    return fields


# ---------------------------------------------------------------------------
# Source 2: QS Rankings
# ---------------------------------------------------------------------------

_QS_SEARCH_URL = "https://www.topuniversities.com/universities/"

def _scrape_qs_ranking(name: str, country: str) -> dict:
    """Try to find university on QS and extract ranking + stats."""
    fields = {}

    # QS has a structured search — try to find the university page
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    search_url = f"https://www.topuniversities.com/universities/{slug}"

    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for ranking badge
        rank_el = soup.select_one("[class*='rank'], .ranking-badge, .qs-ranking")
        if rank_el:
            rank_text = clean_text(rank_el.get_text())
            rank_match = re.search(r"#?\d[\d\-\+]*", rank_text)
            if rank_match:
                fields["global_rank"] = {
                    "value": f"QS {rank_match.group()}", "source": search_url, "confidence": 0.9,
                }

        # Look for stats cards (students, faculty ratio, international)
        for stat in soup.select("[class*='stat'], [class*='key-fact'], .indicator"):
            text = clean_text(stat.get_text(" ")).lower()
            val = clean_text(stat.get_text())

            if "student" in text and "faculty" not in text:
                n = normalize_int(val)
                if n:
                    fields["number_of_students"] = {
                        "value": n, "source": search_url, "confidence": 0.85,
                    }
            elif "faculty" in text or "staff" in text:
                ratio = re.search(r"(\d+\.?\d*)", val)
                if ratio:
                    fields["student_to_faculty_ratio"] = {
                        "value": ratio.group(1), "source": search_url, "confidence": 0.85,
                    }
            elif "international" in text:
                pct = re.search(r"(\d+\.?\d*)\s*%?", val)
                if pct:
                    fields["international_student_ratio"] = {
                        "value": pct.group(1) + "%", "source": search_url, "confidence": 0.8,
                    }

    except Exception as exc:
        logger.debug("QS search failed for %s: %s", name, exc)

    return fields


# ---------------------------------------------------------------------------
# Source 3: Official university website
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_CONTACT_PERSON_RE = re.compile(
    r"(?:dean|director|head|officer|registrar|coordinator|contact\s*person)"
    r"\s*(?:of\s+)?(?:admissions?|enrollment|enrolment)?\s*[:–—-]\s*"
    r"(?:(?:Dr|Prof|Mr|Ms|Mrs|Shri|Smt)\.?\s+)?"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    re.IGNORECASE,
)

_SUBPAGE_KEYWORDS = {
    "contact": ["contact", "contact-us", "reach-us", "enquiry", "get-in-touch",
                 "connect", "helpdesk"],
    "campus": ["student-life", "campus-life", "campus", "facilities", "hostel",
               "sports", "student-affairs", "life-at", "student-services"],
    "admissions": ["admission", "admissions", "apply", "enrol", "enroll",
                   "prospective"],
    "about": ["about", "about-us", "overview", "the-university", "our-university"],
}


def _find_subpage_links(soup, base_url: str) -> dict[str, str]:
    """Scan homepage <a> tags and return {category: url} for key subpages."""
    from urllib.parse import urljoin, urlparse
    base_domain = urlparse(base_url).netloc.lower().replace("www.", "")
    found: dict[str, str] = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        link_domain = parsed.netloc.lower().replace("www.", "")
        if link_domain != base_domain:
            continue
        slug = (parsed.path + " " + a.get_text(" ", strip=True)).lower()
        for category, keywords in _SUBPAGE_KEYWORDS.items():
            if category in found:
                continue
            if any(kw in slug for kw in keywords):
                found[category] = normalize_url(full)
                break
    return found


def _fetch_page(url: str) -> BeautifulSoup | None:
    try:
        resp = get_with_http_fallback(
            requests, url, headers=HEADERS, timeout=8, allow_redirects=True,
        )
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, "html.parser")
    except Exception:
        pass
    return None


def _extract_contact_person(text: str) -> str:
    m = _CONTACT_PERSON_RE.search(text)
    return clean_text(m.group(1)) if m else ""


def _extract_campus_life(soup) -> str:
    """Extract substantial text about campus/student life from a page."""
    paragraphs = []
    for el in soup.find_all(["p", "li", "div"]):
        t = clean_text(el.get_text(" "))
        if len(t) > 40 and not t.startswith(("©", "Copyright", "cookie", "Cookie")):
            paragraphs.append(t)
        if len(paragraphs) >= 6:
            break
    combined = " ".join(paragraphs)
    if len(combined) > 500:
        combined = combined[:500].rsplit(" ", 1)[0]
    return combined


def _scrape_official_site(website: str, name: str) -> dict:
    """Scrape the university's own site: homepage + Contact, Student Life,
    Admissions, About pages for comprehensive data extraction."""
    from urllib.parse import urljoin
    fields = {}

    try:
        resp = get_with_http_fallback(
            requests, website, headers=HEADERS, timeout=12, allow_redirects=True,
        )
        if resp.status_code != 200:
            return {}

        home_soup = BeautifulSoup(resp.text, "html.parser")
        resolved_website = normalize_url(resp.url)
        if resolved_website:
            fields["_resolved_website"] = {
                "value": resolved_website, "source": resolved_website, "confidence": 1.0,
            }

        subpage_links = _find_subpage_links(home_soup, resp.url)
        pages = [("homepage", home_soup, website)]
        for category, url in subpage_links.items():
            sub_soup = _fetch_page(url)
            if sub_soup:
                pages.append((category, sub_soup, url))

        all_emails: list[str] = []
        all_phones: list[str] = []
        contact_person = ""

        for page_type, soup, page_url in pages:
            text = soup.get_text(" ", strip=True)

            for email in _EMAIL_RE.findall(text):
                if email.lower() not in [e.lower() for e in all_emails]:
                    all_emails.append(email)

            for raw_phone in PHONE_RE.findall(text):
                phone = normalize_phone(raw_phone)
                if phone and phone not in all_phones:
                    all_phones.append(phone)

            if not contact_person or page_type in ("contact", "admissions"):
                cp = _extract_contact_person(text)
                if cp:
                    contact_person = cp

            if page_type in ("campus", "about"):
                campus_text = _extract_campus_life(soup)
                if len(campus_text) > len(fields.get("campus_student_life", {}).get("value", "")):
                    fields["campus_student_life"] = {
                        "value": campus_text, "source": page_url, "confidence": 0.7,
                    }

            if page_type == "admissions" and "admissions_page_link" not in fields:
                fields["admissions_page_link"] = {
                    "value": page_url, "source": page_url, "confidence": 0.85,
                }
            elif "admissions_page_link" not in fields:
                for a in soup.find_all("a", href=True):
                    href = a["href"].lower()
                    link_text = a.get_text(" ", strip=True).lower()
                    if any(kw in href or kw in link_text for kw in
                           ["admis", "apply", "enrol", "enroll"]):
                        full_url = normalize_url(urljoin(page_url, a["href"]))
                        if full_url:
                            fields["admissions_page_link"] = {
                                "value": full_url, "source": page_url, "confidence": 0.75,
                            }
                            break

            if "financials" not in fields:
                for text_block in soup.find_all(["p", "div", "span", "td"]):
                    block_text = text_block.get_text(" ", strip=True)
                    if re.search(r"tuition|fee|cost|scholarship", block_text, re.IGNORECASE):
                        money = re.search(
                            r"(?:[$€£¥₹₫₩]|USD|EUR|GBP|INR|VND|JPY)\s*[\d,]+(?:\.\d+)?"
                            r"(?:\s*[-–]\s*[\d,]+(?:\.\d+)?)?",
                            block_text,
                        )
                        if money:
                            fields["financials"] = {
                                "value": money.group(), "source": page_url, "confidence": 0.6,
                            }
                            break

        # Best email (admissions-related preferred)
        admission_emails = [e for e in all_emails if any(k in e.lower() for k in
                           ["admis", "info@", "enquir", "contact", "office", "registrar"])]
        if admission_emails:
            fields["admissions_contact"] = {
                "value": admission_emails[0], "source": website, "confidence": 0.75,
            }
        elif all_emails:
            fields["admissions_contact"] = {
                "value": all_emails[0], "source": website, "confidence": 0.5,
            }

        if all_phones:
            fields["admissions_phone"] = {
                "value": all_phones[0], "source": website, "confidence": 0.65,
            }

        if contact_person:
            fields["contact_person"] = {
                "value": contact_person, "source": website, "confidence": 0.6,
            }

    except Exception as exc:
        logger.debug("Official site scrape failed for %s: %s", name, exc)

    return fields


# ---------------------------------------------------------------------------
# Batch scraper for a pipeline run
# ---------------------------------------------------------------------------

def enrich_run_from_web_sources(run, concurrency: int = 6, progress_callback=None):
    """Scrape all valid seeds in a run from multiple web sources.

    Updates ExtractedUniversity fields that are still empty with scraped data.
    Runs concurrently for speed.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from academic_etl.models import ExtractedUniversity, FieldEvidence, InstitutionSeed
    from django.db import OperationalError
    from django.utils import timezone

    seeds = list(run.seeds.filter(status__in=[
        InstitutionSeed.Status.VALID, InstitutionSeed.Status.CRAWLED,
    ]))
    universities_by_seed = {
        university.seed_id: university
        for university in ExtractedUniversity.objects.filter(
            pipeline_run=run,
            seed_id__in=[seed.pk for seed in seeds],
        )
    }

    now = timezone.now()
    enriched = 0
    processed = 0
    if progress_callback:
        progress_callback(processed=0, total=len(seeds))

    def _save_progress(done=False):
        stats = {
            "processed": processed,
            "total": len(seeds),
            "enriched": enriched,
            "done": done,
        }
        run.stats_json = {**run.stats_json, "web_scrape": stats}
        run.worker_heartbeat_at = timezone.now()
        for attempt in range(3):
            try:
                run.save(update_fields=["stats_json", "worker_heartbeat_at", "updated_at"])
                return
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == 2:
                    logger.warning("Could not persist web-scrape progress: %s", exc)
                    return
                time.sleep(0.25 * (attempt + 1))

    def _fetch(seed, uni):
        if not uni:
            return seed, uni, {}
        result = scrape_university_multi_source(
            name=uni.name or seed.name,
            country=run.country_name,
            country_code=run.country_code,
            website=uni.website or seed.website,
            wikipedia_url=seed.wikipedia_url,
        )
        return seed, uni, result

    def _apply(seed, uni, result):
        if not result:
            return None

        changed = False
        resolved_website = normalize_url(result.get("_resolved_website", ""))
        if resolved_website and normalize_url(uni.website) != resolved_website:
            uni.website = resolved_website
            if seed.website != resolved_website:
                seed.website = resolved_website
                seed.save(update_fields=["website"])
            changed = True
            FieldEvidence.objects.create(
                entity_type="university", entity_id=uni.pk,
                field_name="website", extracted_value=resolved_website,
                normalized_value=resolved_website, source_url=resolved_website,
                page_type="homepage", confidence_score=1.0,
                extractor_name="official_website_redirect",
                extraction_method="web_scrape", crawled_at=now,
            )
        for field, value in result.items():
            if field.startswith("_"):
                continue
            current = getattr(uni, field, "")
            if not current and value:
                if field == "number_of_students":
                    try:
                        setattr(uni, field, int(value))
                    except (ValueError, TypeError):
                        continue
                else:
                    setattr(uni, field, str(value)[:500])
                changed = True
                FieldEvidence.objects.create(
                    entity_type="university", entity_id=uni.pk,
                    field_name=field, extracted_value=str(value),
                    normalized_value=str(value),
                    source_url="multi_source_scrape",
                    page_type="web_scrape",
                    confidence_score=0.7,
                    extractor_name="multi_source_scraper",
                    extraction_method="web_scrape",
                    crawled_at=now,
                )
        if changed:
            uni.save()
        return uni if changed else None

    _save_progress(done=False)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_fetch, seed, universities_by_seed.get(seed.pk)): seed
            for seed in seeds
        }
        for f in as_completed(futures):
            processed += 1
            seed = futures[f]
            uni = universities_by_seed.get(seed.pk)
            try:
                seed, uni, result = f.result()
                if _apply(seed, uni, result) is not None:
                    enriched += 1
            except Exception as exc:
                logger.debug("Multi-source enrichment error: %s", exc)
            if processed % 10 == 0 or processed == len(seeds):
                logger.info("Web scraping: %d/%d universities processed", processed, len(seeds))
                _save_progress(done=False)
            if progress_callback:
                try:
                    progress_callback(
                        processed=processed,
                        total=len(seeds),
                        current_item=seed.name,
                        current_url=(uni.website if uni else seed.website),
                        enriched=enriched,
                    )
                except Exception:
                    for pending in futures:
                        pending.cancel()
                    raise

    _save_progress(done=True)
    logger.info("Multi-source scraping complete: enriched %d/%d universities", enriched, len(seeds))
    return enriched
