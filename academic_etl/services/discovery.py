"""Country-based institution discovery.

Providers:
- wikipedia: English Wikipedia "List of universities in …" articles (broadest roster).
- wikidata: Wikidata Query Service (SPARQL) — name, country + ISO code, city /
  region, official website, Wikipedia URL, Wikidata QID (see services/wikidata.py).
- csv: seed from a University_Import_Clean-style CSV (also fills staging
  ExtractedUniversity rows because the CSV already carries full field data).

Every discovered institution is classified (higher-education vs not) before it
is stored; only seeds with status=valid are ever crawled.
"""

import logging

import requests
from django.utils import timezone

from academic_etl.models import (
    Country,
    ExtractedUniversity,
    FieldEvidence,
    InstitutionSeed,
    PipelineRun,
)

from .classification import classify_institution
from .country_registry import resolve_country  # noqa: F401 — re-exported for callers
from .csv_seed import parse_csv_rows
from .normalize import make_slug, normalize_url
from .wikidata import WikidataSeedProvider
from .wikipedia import WikipediaListProvider

logger = logging.getLogger(__name__)


def _extract_domain(url: str) -> str:
    """Extract bare domain from URL for dedup comparison."""
    if not url:
        return ""
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host


def ensure_country(name: str, code: str) -> Country | None:
    """Fetch-or-create the reference Country. Both name and code are unique, so
    match on either before inserting and never raise (a stale row with a
    different code must not break discovery)."""
    if not name or not code:
        return None
    obj = Country.objects.filter(code=code).first() or Country.objects.filter(name=name).first()
    if obj:
        return obj
    from django.db import IntegrityError
    try:
        return Country.objects.create(name=name, code=code)
    except IntegrityError:
        return (Country.objects.filter(code=code).first()
                or Country.objects.filter(name=name).first())


def discover_wikidata(country_name: str, country_code: str, limit: int = 200) -> list[dict]:
    """Discover higher-education institutions for a country from Wikidata."""
    return WikidataSeedProvider().discover(country_name, country_code, limit)


def discover_wikipedia(country_name: str, country_code: str, limit: int = 0) -> list[dict]:
    """Discover institutions from the country's Wikipedia list article."""
    return WikipediaListProvider().discover(country_name, country_code, limit)


def discover_csv(csv_path: str, country_name: str, country_code: str, limit: int = 0) -> list[dict]:
    records = parse_csv_rows(csv_path)
    seeds = []
    for rec in records:
        f = rec.get("fields", {})
        rec_country = f.get("country") or country_name
        if country_name and rec_country and rec_country.lower() != country_name.lower():
            continue
        seeds.append({
            "name": f.get("name") or "(unaligned CSV row)",
            "country": rec_country or country_name,
            "country_code": f.get("country_code") or country_code,
            "region": "",
            "website": (f.get("normalized") or {}).get("website", ""),
            "source_url": "",
            "source_name": "csv",
            "raw_json": rec["raw"],
            "_csv_record": rec,
        })
        if limit and len(seeds) >= limit:
            break
    return seeds


def run_discovery(run: PipelineRun, limit: int = 100, csv_path: str = "") -> list[InstitutionSeed]:
    """Discover institutions for run.country, classify and persist them."""
    run.status = PipelineRun.Status.DISCOVERING
    run.save(update_fields=["status", "updated_at"])

    if run.seed_provider == "csv":
        raw_seeds = discover_csv(csv_path, run.country_name, run.country_code, limit)
    elif run.seed_provider == "wikidata":
        raw_seeds = discover_wikidata(run.country_name, run.country_code, limit)
    else:
        # Combine Wikipedia + Wikidata for maximum coverage
        raw_seeds = discover_wikipedia(run.country_name, run.country_code, limit)
        wiki_names = {s["name"].strip().lower() for s in raw_seeds}
        wiki_domains = {
            _extract_domain(s["website"]) for s in raw_seeds if s.get("website")
        }
        try:
            wd_seeds = discover_wikidata(run.country_name, run.country_code, limit or 500)
            for s in wd_seeds:
                name_key = s["name"].strip().lower()
                domain = _extract_domain(s.get("website", ""))
                if name_key not in wiki_names and (not domain or domain not in wiki_domains):
                    raw_seeds.append(s)
                    wiki_names.add(name_key)
                    if domain:
                        wiki_domains.add(domain)
            logger.info("Combined discovery: %d Wikipedia + %d extra from Wikidata = %d total",
                        len(wiki_names) - len(wd_seeds) + len(raw_seeds), len(wd_seeds), len(raw_seeds))
        except Exception as exc:
            logger.warning("Wikidata discovery failed, proceeding with Wikipedia only: %s", exc)
        # Source 3: Web discovery (UniRank + Wikipedia categories)
        try:
            from .web_discover import discover_from_web
            web_seeds = discover_from_web(run.country_name, run.country_code, limit or 500)
            added = 0
            for s in web_seeds:
                name_key = s["name"].strip().lower()
                domain = _extract_domain(s.get("website", ""))
                if name_key not in wiki_names and (not domain or domain not in wiki_domains):
                    raw_seeds.append(s)
                    wiki_names.add(name_key)
                    if domain:
                        wiki_domains.add(domain)
                    added += 1
            if added:
                logger.info("Web discovery added %d more institutions for %s", added, run.country_name)
        except Exception as exc:
            logger.warning("Web discovery failed: %s", exc)

    ensure_country(run.country_name, run.country_code)

    # Already-known Wikidata QIDs in this run -> never stage the same entity twice.
    seen_qids = set(
        run.seeds.exclude(wikidata_qid="").values_list("wikidata_qid", flat=True)
    )

    created = []
    stats = {"valid": 0, "invalid": 0, "needs_review": 0}
    for raw in raw_seeds:
        qid = raw.get("wikidata_qid", "")
        if qid and qid in seen_qids:
            continue
        itype, status, confidence = classify_institution(raw["name"], raw["website"])
        # Providers that carry their own (metadata-completeness) confidence win.
        if raw.get("confidence") is not None:
            confidence = max(confidence, raw["confidence"])
        seed, was_created = InstitutionSeed.objects.get_or_create(
            pipeline_run=run, name=raw["name"][:500],
            city=raw.get("city", "")[:255], website=raw["website"][:500],
            defaults={
                "country": raw["country"][:100],
                "country_code": (raw["country_code"] or run.country_code)[:2],
                "region": raw["region"][:255],
                "institution_type": itype,
                "status": status,
                "confidence_score": confidence,
                "source_url": raw["source_url"][:500],
                "source_name": raw["source_name"],
                "wikidata_qid": qid[:20],
                "wikipedia_url": raw.get("wikipedia_url", "")[:500],
                "raw_json": raw["raw_json"],
            },
        )
        if qid:
            seen_qids.add(qid)
        if was_created:
            stats[
                "valid" if status == InstitutionSeed.Status.VALID
                else "invalid" if status == InstitutionSeed.Status.INVALID
                else "needs_review"
            ] += 1
            created.append(seed)
            if "_csv_record" in raw:
                _stage_university_from_csv(run, seed, raw["_csv_record"])

    run.total_discovered_institutions = run.seeds.count()
    run.stats_json = {**run.stats_json, "discovery": stats}
    run.status = PipelineRun.Status.REVIEW if run.crawl_mode == "discover_only" else run.status
    run.save()
    logger.info(
        "Run %s: discovered %s seeds (%s valid, %s invalid, %s needs_review)",
        run.pk, len(created), stats["valid"], stats["invalid"], stats["needs_review"],
    )
    return created


def _stage_university_from_csv(run: PipelineRun, seed: InstitutionSeed, rec: dict):
    """CSV rows already contain full university data: stage them with evidence."""
    f = rec.get("fields", {})
    norm = f.get("normalized", {})
    if rec.get("suspicious") or not f.get("name"):
        uni = ExtractedUniversity.objects.create(
            pipeline_run=run, seed=seed, name=f.get("name", ""),
            country=run.country_name, country_code=run.country_code,
            raw_json=rec["raw"], validation_status="needs_review",
        )
        return uni

    uni = ExtractedUniversity.objects.create(
        pipeline_run=run,
        seed=seed,
        name=f.get("name", "")[:500],
        location=f.get("location", "")[:500],
        description=f.get("description", ""),
        slug=(norm.get("slug") or make_slug(f.get("name", "")))[:490],
        sponsored=False,
        website=norm.get("website", "")[:500],
        global_rank=f.get("global_rank", "")[:100],
        financials=f.get("financials", "")[:500],
        student_loan_available=norm.get("student_loan_available"),
        campus_student_life=f.get("campus_student_life", ""),
        number_of_students=norm.get("number_of_students"),
        student_to_faculty_ratio=f.get("student_to_faculty_ratio", "")[:50],
        international_student_ratio=f.get("international_student_ratio", "")[:50],
        housing_availability=norm.get("housing_availability"),
        admissions_contact=norm.get("admissions_contact", "")[:254],
        admissions_phone=norm.get("admissions_phone", "")[:50],
        contact_person=f.get("contact_person", "")[:255],
        admissions_page_link=norm.get("admissions_page_link", "")[:500],
        immigration_support=norm.get("immigration_support"),
        university_campuses=norm.get("university_campuses"),
        country=f.get("country") or run.country_name,
        country_code=(f.get("country_code") or run.country_code)[:2],
        institution_type=seed.institution_type,
        raw_json=rec["raw"],
        normalized_json={k: v for k, v in norm.items()},
        confidence_score=0.8,  # human-curated CSV: fairly trustworthy
    )

    now = timezone.now()
    evidences = []
    for field, value in f.items():
        if field in ("normalized", "country", "country_code") or value in ("", None):
            continue
        normalized_value = norm.get(field, value)
        evidences.append(FieldEvidence(
            entity_type="university",
            entity_id=uni.pk,
            field_name=field,
            extracted_value=str(value)[:5000],
            normalized_value="" if normalized_value is None else str(normalized_value)[:5000],
            source_url="",
            page_type="csv",
            text_snippet=str(value)[:500],
            confidence_score=0.8,
            extractor_name="csv_seed",
            extraction_method="csv",
            crawled_at=now,
        ))
    FieldEvidence.objects.bulk_create(evidences)
    return uni
