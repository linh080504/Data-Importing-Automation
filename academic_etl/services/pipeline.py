"""Per-institution crawl orchestration: crawl site -> store pages -> extract
university fields + programs -> staging rows + FieldEvidence."""

import logging

from bs4 import BeautifulSoup
from django.conf import settings
from django.utils import timezone

from academic_etl.models import (
    CrawledPage,
    DegreeLevel,
    ExtractedProgram,
    ExtractedUniversity,
    FieldEvidence,
    InstitutionSeed,
    PipelineRun,
    ValidationStatus,
)

from .crawler import SiteCrawler
from .extraction import classify_degree_level, extract_programs, extract_university_fields
from .normalize import make_slug, normalize_phone, normalize_program_name, normalize_url, url_domain
from .program_detail import extract_program_detail
from .reconcile import (
    KB_SOURCES,
    build_official_website_evidence,
    build_source_evidence,
    detect_conflicts,
)

logger = logging.getLogger(__name__)

# staging fields that may be filled from crawl extraction
_CRAWL_FILLABLE = {
    "name", "description", "admissions_contact", "admissions_phone",
    "admissions_page_link", "financials", "campus_student_life", "number_of_students",
    "international_student_ratio",
}

# program fields that may be filled from a crawled program DETAIL page
_PROGRAM_DETAIL_FILLABLE = {
    "field_of_study", "faculty_or_school", "description", "duration", "study_mode",
    "language", "tuition_fee", "currency", "intake", "application_deadline",
    "admission_requirements", "career_outcomes", "accreditation",
}


def crawl_seed(run: PipelineRun, seed: InstitutionSeed, crawler: SiteCrawler) -> ExtractedUniversity | None:
    """Crawl one valid institution seed and persist everything extracted."""
    if not seed.website:
        seed.status = InstitutionSeed.Status.SKIPPED
        seed.save(update_fields=["status"])
        logger.info("seed %s (%s) skipped: no website", seed.pk, seed.name)
        return None

    logger.info("crawling seed %s: %s -> %s", seed.pk, seed.name, seed.website)
    pages = crawler.crawl_site(seed.website)
    fetched_ok = [p for p in pages if p.get("html")]

    page_rows = []
    for p in pages:
        page_rows.append(CrawledPage.objects.create(
            pipeline_run=run,
            seed=seed,
            url=p["url"][:1000],
            final_url=(p.get("final_url") or "")[:1000],
            page_type=p["page_type"],
            status_code=p.get("status_code"),
            title=p.get("title", "")[:500],
            depth=p.get("depth", 0),
            html_hash=p.get("html_hash", ""),
            html_cache_path=p.get("cache_path", ""),
            render_engine=p.get("fetch_method", "requests"),
            fetch_error=p.get("error", ""),
        ))

    if not fetched_ok:
        seed.status = InstitutionSeed.Status.CRAWL_FAILED
        seed.save(update_fields=["status"])
        logger.warning("seed %s (%s): no page fetched", seed.pk, seed.name)
        return None

    # reuse a CSV-staged university for this seed if present, else create
    uni = ExtractedUniversity.objects.filter(pipeline_run=run, seed=seed).first()
    if uni is None:
        from .country_registry import get_numeric_code
        uni = ExtractedUniversity.objects.create(
            pipeline_run=run, seed=seed,
            name=seed.name, website=seed.website,
            location=get_numeric_code(seed.country_code) or seed.country,
            country=seed.country, country_code=seed.country_code,
            city=seed.city, region=seed.region,
            institution_type=seed.institution_type,
            slug=make_slug(seed.name, seed.city),
            confidence_score=seed.confidence_score,
            sponsored=False,
        )

    # Keep the review/export link on the scheme and redirect target that the
    # crawler actually reached. This also preserves HTTP-only university sites.
    homepage = next((p for p in fetched_ok if p.get("page_type") == "homepage"), None)
    resolved_website = normalize_url((homepage or {}).get("final_url", ""))
    if resolved_website:
        uni.website = resolved_website

    extracted = extract_university_fields(pages)
    now = timezone.now()
    filled, evidences = 0, []
    for field, ev in extracted.items():
        if field not in _CRAWL_FILLABLE or ev["value"] in ("", None):
            continue
        current = getattr(uni, field, None)
        # never clobber existing (e.g. CSV-seeded) values with crawl guesses
        if current in ("", None):
            value = ev["value"]
            if field == "number_of_students":
                value = int(value) if str(value).isdigit() else None
            elif field == "admissions_phone":
                value = normalize_phone(value)
                if not value:
                    continue
            setattr(uni, field, value)
            filled += 1
        evidences.append(FieldEvidence(
            entity_type="university", entity_id=uni.pk, field_name=field,
            extracted_value=str(ev["value"])[:5000],
            normalized_value=str(ev["value"])[:5000],
            source_url=ev["source_url"][:1000], page_title=ev["page_title"][:500],
            page_type=ev["page_type"], css_selector=ev["css_selector"][:255],
            text_snippet=ev["text_snippet"], confidence_score=ev["confidence"],
            extractor_name=ev["extractor"], extraction_method="rule",
            crawled_at=now, raw_html_hash=ev["raw_html_hash"],
        ))
    # ---- cross-source reconciliation (KB seed vs official website) ---------
    source_conflicts = []
    if seed.source_name in KB_SOURCES:
        evidences.extend(build_source_evidence(uni, seed, now))
        evidences.extend(build_official_website_evidence(uni, pages, now))
        source_conflicts = detect_conflicts(seed, extracted, pages)

    if not uni.slug and uni.name:
        uni.slug = make_slug(uni.name, uni.city)
    uni.normalized_json = {**uni.normalized_json,
                           "crawl_extracted": {k: str(v["value"])[:300] for k, v in extracted.items()}}
    if source_conflicts:
        uni.normalized_json["source_conflicts"] = source_conflicts
        logger.info("seed %s (%s): source conflicts on %s", seed.pk, seed.name, source_conflicts)
    uni.save()
    if resolved_website and seed.website != resolved_website:
        seed.website = resolved_website
        seed.save(update_fields=["website"])
    FieldEvidence.objects.bulk_create(evidences)

    # ---- programs ----------------------------------------------------------
    program_candidates = extract_programs(pages)
    created_programs = 0
    seen_keys = set(
        (normalize_program_name(p.program_name), p.degree_level)
        for p in uni.programs.all()
    )
    new_programs = []
    for cand in program_candidates:
        key = (normalize_program_name(cand["program_name"]), cand["degree_level"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        is_he = cand["is_higher_education_program"]
        program = ExtractedProgram.objects.create(
            pipeline_run=run,
            extracted_university=uni,
            university_slug=uni.slug,
            country=uni.country, country_code=uni.country_code,
            program_name=cand["program_name"],
            degree_level=cand["degree_level"],
            program_url=cand["program_url"],
            source_url=cand["evidence"]["source_url"][:1000],
            is_higher_education_program=is_he,
            confidence_score=cand["confidence"],
            raw_json={"candidate": {k: v for k, v in cand.items() if k != "evidence"}},
            validation_status=(
                ValidationStatus.NEEDS_REVIEW
                if is_he is None or cand["degree_level"] == DegreeLevel.NON_DEGREE
                else ValidationStatus.NOT_VALIDATED
            ),
        )
        ev = cand["evidence"]
        FieldEvidence.objects.create(
            entity_type="program", entity_id=program.pk, field_name="program_name",
            extracted_value=ev["value"][:5000], normalized_value=cand["program_name"][:5000],
            source_url=ev["source_url"][:1000], page_title=ev["page_title"][:500],
            page_type=ev["page_type"], css_selector=ev["css_selector"][:255],
            text_snippet=ev["text_snippet"], confidence_score=ev["confidence"],
            extractor_name=ev["extractor"], extraction_method="rule",
            crawled_at=now, raw_html_hash=ev["raw_html_hash"],
        )
        created_programs += 1
        new_programs.append(program)

    # ---- program detail-page crawl (per-program enrichment) ----------------
    enriched = crawl_program_details(run, uni, seed, new_programs, crawler)

    seed.status = InstitutionSeed.Status.CRAWLED
    seed.save(update_fields=["status"])
    logger.info("seed %s (%s): %s pages, %s fields filled, %s programs (%s detail-enriched)",
                seed.pk, seed.name, len(fetched_ok), filled, created_programs, enriched)
    return uni


def crawl_program_details(run: PipelineRun, uni: ExtractedUniversity,
                          seed: InstitutionSeed, programs: list, crawler: SiteCrawler) -> int:
    """Fetch each program's detail page (same domain, bounded) and enrich it with
    per-field evidence. Reuses the existing SiteCrawler.fetch — no new fetcher."""
    if not getattr(settings, "ETL_CRAWL_PROGRAM_DETAILS", True):
        return 0
    budget = getattr(settings, "ETL_MAX_PROGRAM_DETAIL_PAGES", 12)
    uni_domain = url_domain(uni.website)
    enriched = 0
    for program in programs:
        if enriched >= budget:
            break
        url = program.program_url
        if not url or (uni_domain and url_domain(url) != uni_domain):
            continue
        page = crawler.fetch(url)
        CrawledPage.objects.create(
            pipeline_run=run, seed=seed,
            url=url[:1000], final_url=(page.get("final_url") or "")[:1000],
            page_type="programs", status_code=page.get("status_code"),
            title=(page.get("title") or "")[:500], depth=2,
            html_hash=page.get("html_hash", ""), html_cache_path=page.get("cache_path", ""),
            render_engine=page.get("fetch_method", "requests"), fetch_error=page.get("error", ""),
        )
        if not page.get("html"):
            continue
        soup = BeautifulSoup(page["html"], "html.parser")
        page["soup"] = soup
        title_tag = soup.find("title")
        page["title"] = title_tag.get_text(strip=True)[:500] if title_tag else ""
        page["page_type"] = "programs"
        detail = extract_program_detail(page)
        if _apply_program_detail(program, detail, page, timezone.now()):
            enriched += 1
    return enriched


def _apply_program_detail(program: ExtractedProgram, detail: dict, page: dict, now) -> bool:
    """Fill empty program fields from detail evidence, record FieldEvidence for
    every extracted field, and refine degree level / non-degree flagging."""
    if not detail:
        return False
    source_url = page.get("final_url") or page.get("url", "")
    if not program.source_url:
        program.source_url = source_url[:1000]

    evidences = []
    for field, ev in detail.items():
        value = ev["value"]
        if value in ("", None):
            continue
        if field in _PROGRAM_DETAIL_FILLABLE and not getattr(program, field, ""):
            setattr(program, field, value)
        if field in _PROGRAM_DETAIL_FILLABLE or field == "program_name":
            evidences.append(_program_field_evidence(program, field, ev, now))

    # Refine degree level using the richer detail text (name + description +
    # page body, so non-degree markers like "workshop"/"bootcamp" are caught).
    desc = (detail.get("description") or {}).get("value", "")
    soup = page.get("soup")
    page_text = soup.get_text(" ", strip=True)[:800] if soup is not None else ""
    level, is_he, conf = classify_degree_level(f"{program.program_name} {desc} {page_text}")
    if is_he is False:  # short course / workshop / bootcamp / language prep / certificate
        program.degree_level = DegreeLevel.NON_DEGREE
        program.is_higher_education_program = False
        program.validation_status = ValidationStatus.NEEDS_REVIEW
        evidences.append(_program_field_evidence(
            program, "degree_level",
            {"value": DegreeLevel.NON_DEGREE, "source_url": source_url, "page_title": page.get("title", ""),
             "page_type": "programs", "css_selector": "", "text_snippet": desc[:500],
             "confidence": conf, "extractor": "degree_classifier", "raw_html_hash": page.get("html_hash", "")}, now))
    elif program.degree_level == DegreeLevel.UNKNOWN and level != DegreeLevel.UNKNOWN:
        program.degree_level = level
        if program.is_higher_education_program is None:
            program.is_higher_education_program = is_he
        evidences.append(_program_field_evidence(
            program, "degree_level",
            {"value": level, "source_url": source_url, "page_title": page.get("title", ""),
             "page_type": "programs", "css_selector": "", "text_snippet": desc[:500],
             "confidence": conf, "extractor": "degree_classifier", "raw_html_hash": page.get("html_hash", "")}, now))

    program.raw_json = {**program.raw_json, "detail_crawled": True}
    program.save()
    FieldEvidence.objects.bulk_create(evidences)
    return True


def _program_field_evidence(program, field, ev, now) -> FieldEvidence:
    return FieldEvidence(
        entity_type="program", entity_id=program.pk, field_name=field,
        extracted_value=str(ev["value"])[:5000], normalized_value=str(ev["value"])[:5000],
        source_url=ev["source_url"][:1000], page_title=ev["page_title"][:500],
        page_type=ev["page_type"], css_selector=ev["css_selector"][:255],
        text_snippet=ev["text_snippet"], confidence_score=ev["confidence"],
        extractor_name=ev["extractor"], extraction_method="rule",
        crawled_at=now, raw_html_hash=ev["raw_html_hash"],
    )


def crawl_run(run: PipelineRun, limit: int = 0, crawler: SiteCrawler | None = None,
              concurrency: int = 5, progress_callback=None) -> dict:
    """Crawl all valid (higher-education) seeds of a run.

    Uses concurrent crawling (default 5 workers) for speed while maintaining
    per-domain rate limits. Each worker gets its own SiteCrawler instance.
    DB writes are serialized via a lock.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    crawler = crawler or SiteCrawler()
    run.status = PipelineRun.Status.CRAWLING
    run.worker_heartbeat_at = timezone.now()
    run.save(update_fields=["status", "worker_heartbeat_at", "updated_at"])

    seed_list = list(
        run.seeds.filter(status=InstitutionSeed.Status.VALID).exclude(website="")
        .values_list("pk", flat=True)
    )
    if limit:
        seed_list = seed_list[:limit]

    stats = {"attempted": 0, "crawled": 0, "failed": 0}
    db_lock = threading.Lock()
    if progress_callback:
        progress_callback(processed=0, total=len(seed_list))

    def _crawl_one(seed_pk):
        seed = InstitutionSeed.objects.get(pk=seed_pk)
        worker_crawler = SiteCrawler(
            max_pages=crawler.max_pages,
            max_depth=crawler.max_depth,
            country_code=crawler.country_code,
        )
        try:
            uni = crawl_seed(run, seed, worker_crawler)
            with db_lock:
                stats["attempted"] += 1
                if uni is not None:
                    stats["crawled"] += 1
                else:
                    stats["failed"] += 1
                if stats["attempted"] % 5 == 0:
                    run.total_crawled_institutions = stats["crawled"]
                    run.stats_json = {**run.stats_json, "crawl": stats}
                    run.worker_heartbeat_at = timezone.now()
                    run.save(update_fields=[
                        "total_crawled_institutions", "stats_json",
                        "worker_heartbeat_at", "updated_at",
                    ])
        except Exception as exc:
            with db_lock:
                stats["attempted"] += 1
                stats["failed"] += 1
            logger.warning("Crawl failed for seed %s (%s): %s", seed_pk, seed.name, exc)

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(_crawl_one, pk): pk for pk in seed_list}
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass
                if progress_callback:
                    seed = InstitutionSeed.objects.get(pk=futures[f])
                    try:
                        progress_callback(
                            processed=stats["attempted"],
                            total=len(seed_list),
                            current_item=seed.name,
                            current_url=seed.website,
                            crawled=stats["crawled"],
                            errors=stats["failed"],
                        )
                    except Exception:
                        for pending in futures:
                            pending.cancel()
                        raise
    except Exception as exc:
        run.status = PipelineRun.Status.FAILED
        run.error_message = str(exc)[:2000]
        run.stats_json = {**run.stats_json, "crawl": stats}
        run.save()
        raise

    run.total_crawled_institutions = run.seeds.filter(status=InstitutionSeed.Status.CRAWLED).count()
    run.total_programs_found = run.programs.count()
    run.stats_json = {**run.stats_json, "crawl": stats}
    run.status = PipelineRun.Status.REVIEW
    run.save()
    logger.info("run %s crawl finished: %s", run.pk, stats)
    return stats


# fields fillable from a Wikipedia article (the English backbone)
_WIKI_FILLABLE = {"description", "website", "number_of_students", "city"}


def enrich_from_wikipedia(run: PipelineRun, seed: InstitutionSeed,
                          html: str | None = None) -> ExtractedUniversity | None:
    """Stage an English ExtractedUniversity from the seed's Wikipedia article and
    backfill ``seed.website`` so the official-site crawl can follow. ``html`` may
    be a prefetched article body. Returns the university (or None if no article)."""
    if not seed.wikipedia_url:
        return None
    from .wikipedia_extract import extract_wikipedia_university
    detail = extract_wikipedia_university(seed.wikipedia_url, seed.country, html=html)

    uni = ExtractedUniversity.objects.filter(pipeline_run=run, seed=seed).first()
    if uni is None:
        from .country_registry import get_numeric_code
        uni = ExtractedUniversity.objects.create(
            pipeline_run=run, seed=seed, name=seed.name, website=seed.website,
            location=get_numeric_code(seed.country_code) or seed.country,
            country=seed.country, country_code=seed.country_code,
            city=seed.city, region=seed.region, institution_type=seed.institution_type,
            slug=make_slug(seed.name, seed.city), confidence_score=seed.confidence_score,
            sponsored=False,
        )

    now = timezone.now()
    evidences, filled = [], 0
    for field, ev in detail.items():
        if field not in _WIKI_FILLABLE or ev["value"] in ("", None):
            continue
        if getattr(uni, field, None) in ("", None):
            setattr(uni, field, ev["value"])
            filled += 1
        evidences.append(FieldEvidence(
            entity_type="university", entity_id=uni.pk, field_name=field,
            extracted_value=str(ev["value"])[:5000], normalized_value=str(ev["value"])[:5000],
            source_url=ev["source_url"][:1000], page_title=ev["page_title"][:500],
            page_type=ev["page_type"], css_selector=ev["css_selector"][:255],
            text_snippet=ev["text_snippet"], confidence_score=ev["confidence"],
            extractor_name=ev["extractor"], extraction_method="wikipedia",
            crawled_at=now, raw_html_hash=ev["raw_html_hash"],
        ))

    if not seed.website and uni.website:  # let the official-site crawl run later
        seed.website = uni.website[:500]
        seed.save(update_fields=["website"])
    if not uni.slug and uni.name:
        uni.slug = make_slug(uni.name, uni.city)
    uni.normalized_json = {**uni.normalized_json,
                           "wikipedia_extracted": {k: str(v["value"])[:200] for k, v in detail.items()}}
    uni.save()
    FieldEvidence.objects.bulk_create(evidences)
    logger.info("wikipedia enrich seed %s (%s): %s fields filled", seed.pk, seed.name, filled)
    return uni


# Fields Gemini grounding is the authoritative source for.
_GEMINI_FILLABLE = {
    "name", "website", "description", "campus_student_life", "number_of_students",
    "financials", "global_rank", "student_to_faculty_ratio",
    "international_student_ratio", "admissions_contact", "admissions_phone",
    "admissions_page_link", "contact_person", "university_campuses",
    "housing_availability", "student_loan_available", "immigration_support",
}
# Confidence assigned to grounded values: high enough to win on import
# (importer overwrites existing non-empty values only at >= 0.8).
_GEMINI_CONFIDENCE = 0.85

# The fields that gate whether a university still "needs" a Gemini call in the
# hybrid (crawl-first) flow. If Wikipedia + crawl already filled all of these, we
# skip Gemini for that institution entirely — saving a request (the free quota is
# counted per request, not per field).
GEMINI_REQUIRED_FIELDS = (
    "name", "website", "description", "campus_student_life",
    "number_of_students", "financials", "global_rank",
    "student_to_faculty_ratio", "international_student_ratio",
    "admissions_contact", "admissions_phone", "admissions_page_link",
    "contact_person", "university_campuses", "housing_availability",
    "student_loan_available", "immigration_support",
)


def _field_filled(uni, field: str) -> bool:
    value = getattr(uni, field, None)
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def apply_country_defaults(uni: ExtractedUniversity, country_code: str) -> None:
    """Set location and sponsored. Boolean/int fields are left as None so the
    AI enrichment step can fill them; post-process applies fallback defaults
    for any that remain None after AI."""
    from .gemini_enrich import country_numeric
    numeric = country_numeric(country_code)
    if numeric:
        uni.location = numeric
    uni.sponsored = False


def enrich_seed_from_gemini(run: PipelineRun, seed: InstitutionSeed, result: dict,
                            overwrite: bool = True) -> ExtractedUniversity | None:
    """Stage/extend an ExtractedUniversity for ``seed`` from a Gemini grounding
    ``result`` (see ``gemini_enrich.enrich_institution``). With ``overwrite``,
    grounded values replace existing staged values (Gemini is the primary source
    for these fields); otherwise only empty fields are filled."""
    fields = result.get("fields") or {}
    if not fields or result.get("error"):
        return None
    sources = result.get("sources") or []
    primary_source = (sources[0] if sources else seed.wikipedia_url or seed.source_url) or ""
    snippet = "; ".join(sources[:5])[:5000]

    uni = ExtractedUniversity.objects.filter(pipeline_run=run, seed=seed).first()
    if uni is None:
        from .country_registry import get_numeric_code
        uni = ExtractedUniversity.objects.create(
            pipeline_run=run, seed=seed, name=seed.name, website=seed.website,
            location=get_numeric_code(seed.country_code) or seed.country,
            country=seed.country, country_code=seed.country_code,
            city=seed.city, region=seed.region, institution_type=seed.institution_type,
            slug=make_slug(seed.name, seed.city), confidence_score=seed.confidence_score,
            sponsored=False,
        )

    apply_country_defaults(uni, seed.country_code)

    now = timezone.now()
    evidences, filled = [], 0
    for field in _GEMINI_FILLABLE:
        value = fields.get(field)
        if value in ("", None):
            continue
        current = getattr(uni, field, None)
        if overwrite or current in ("", None):
            setattr(uni, field, value)
            filled += 1
        evidences.append(FieldEvidence(
            entity_type="university", entity_id=uni.pk, field_name=field,
            extracted_value=str(value)[:5000], normalized_value=str(value)[:5000],
            source_url=primary_source[:1000], page_title="Gemini (Google Search grounding)",
            page_type="grounded_answer", css_selector="",
            text_snippet=snippet, confidence_score=_GEMINI_CONFIDENCE,
            extractor_name="gemini", extraction_method="gemini_grounding",
            crawled_at=now,
        ))

    if uni.website and not seed.website:
        seed.website = uni.website[:500]
        seed.save(update_fields=["website"])
    if not uni.slug and uni.name:
        uni.slug = make_slug(uni.name, uni.city)
    uni.confidence_score = max(uni.confidence_score, _GEMINI_CONFIDENCE)
    uni.normalized_json = {**uni.normalized_json,
                           "gemini_sources": sources[:10],
                           "gemini_fields": {k: str(fields.get(k))[:300] for k in _GEMINI_FILLABLE}}
    uni.save()
    FieldEvidence.objects.bulk_create(evidences)
    logger.info("gemini enrich seed %s (%s): %s fields filled, %s sources",
                seed.pk, seed.name, filled, len(sources))
    return uni


def enrich_run_from_gemini(run: PipelineRun, limit: int = 0, concurrency: int = 0,
                           use_cache: bool = True, overwrite: bool = True,
                           set_status: bool = True, skip_complete: bool = False) -> dict:
    """Enrich valid seeds of a run with Gemini grounded answers. API calls run
    concurrently (IO-bound); DB writes stay serial in this thread. Progress
    (``stats_json["gemini_enrich"]``) is persisted after every institution so the
    web UI can show it live.

    With ``skip_complete`` (the hybrid / quota-saving mode), an institution whose
    ``GEMINI_REQUIRED_FIELDS`` are ALL already filled (by Wikipedia + crawl) is
    skipped entirely — no Gemini request is spent on it. Combine with
    ``overwrite=False`` so Gemini only fills the still-empty fields and never
    clobbers the free crawl/Wikipedia values."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from .gemini_enrich import enrich_institution, is_configured

    if not is_configured():
        raise RuntimeError("No Gemini API key configured — set GEMINI_API_KEY / GEMINI_API_KEYS.")

    all_seeds = list(run.seeds.filter(status=InstitutionSeed.Status.VALID))
    if limit:
        all_seeds = all_seeds[:limit]
    concurrency = concurrency or getattr(settings, "GEMINI_CONCURRENCY", 4)

    # In hybrid mode, decide which seeds still need a Gemini call. Skipped (already
    # complete) universities still get the deterministic defaults applied.
    skipped = 0
    if skip_complete:
        unis = {u.seed_id: u for u in run.universities.filter(seed__in=all_seeds)}
        seeds = []
        for s in all_seeds:
            uni = unis.get(s.pk)
            if uni is not None and all(_field_filled(uni, f) for f in GEMINI_REQUIRED_FIELDS):
                apply_country_defaults(uni, s.country_code)
                uni.save()
                skipped += 1
            else:
                seeds.append(s)
    else:
        seeds = all_seeds

    stats = {"attempted": 0, "staged": 0, "from_cache": 0, "errors": 0,
             "skipped_complete": skipped, "total": len(seeds), "done": False}
    if set_status:
        run.status = PipelineRun.Status.CRAWLING  # generic "active" state for the UI
    run.stats_json = {**run.stats_json, "gemini_enrich": dict(stats)}
    run.save(update_fields=["status", "stats_json", "updated_at"] if set_status
             else ["stats_json", "updated_at"])

    def _fetch(seed):
        return seed, enrich_institution(
            seed.name, seed.country, city=seed.city,
            wikipedia_url=seed.wikipedia_url, country_code=seed.country_code,
            use_cache=use_cache,
        )

    def _handle(seed, result):
        stats["attempted"] += 1
        if result.get("from_cache"):
            stats["from_cache"] += 1
        if result.get("error"):
            stats["errors"] += 1
            logger.warning("gemini seed %s (%s): %s", seed.pk, seed.name, result["error"])
        elif enrich_seed_from_gemini(run, seed, result, overwrite=overwrite) is not None:
            stats["staged"] += 1
        run.stats_json = {**run.stats_json, "gemini_enrich": dict(stats)}
        run.save(update_fields=["stats_json", "updated_at"])

    if concurrency > 1 and seeds:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(_fetch, s) for s in seeds]
            for fut in as_completed(futures):
                seed, result = fut.result()
                _handle(seed, result)
    else:
        for s in seeds:
            seed, result = _fetch(s)
            _handle(seed, result)

    stats["done"] = True
    run.stats_json = {**run.stats_json, "gemini_enrich": dict(stats)}
    run.save(update_fields=["stats_json", "updated_at"])
    logger.info("run %s gemini enrich: %s", run.pk, stats)
    return stats


def enrich_uni_majors_from_gemini(uni: ExtractedUniversity, result: dict) -> int:
    """Create ExtractedProgram rows (1-to-many) for a university from a Gemini
    majors ``result`` (see ``gemini_enrich.enrich_majors``). Returns # created.
    Names carry a FieldEvidence with the grounded source URL. The deliverable only
    needs name + URL, so degree level defaults to bachelor (higher-ed)."""
    majors = result.get("majors") or []
    if not majors or result.get("error"):
        return 0
    programs_page = result.get("programs_page") or ""
    fallback_url = programs_page or (result.get("sources") or [""])[0]
    now = timezone.now()

    existing = set(normalize_program_name(p.program_name) for p in uni.programs.all())
    created = 0
    for major in majors:
        mname = (major.get("name") or "").strip()
        key = normalize_program_name(mname)
        if not mname or key in existing:
            continue
        existing.add(key)
        murl = (major.get("url") or "").strip() or fallback_url
        program = ExtractedProgram.objects.create(
            pipeline_run=uni.pipeline_run, extracted_university=uni,
            university_slug=uni.slug, country=uni.country, country_code=uni.country_code,
            program_name=mname[:500],
            degree_level=DegreeLevel.BACHELOR,
            program_url=murl[:1000], source_url=(murl or programs_page)[:1000],
            is_higher_education_program=True,
            confidence_score=_GEMINI_CONFIDENCE,
            raw_json={"gemini_major": True, "programs_page": programs_page},
        )
        FieldEvidence.objects.create(
            entity_type="program", entity_id=program.pk, field_name="program_name",
            extracted_value=mname[:5000], normalized_value=mname[:5000],
            source_url=murl[:1000], page_title="Gemini (Google Search grounding)",
            page_type="grounded_answer", text_snippet="; ".join(result.get("sources") or [])[:5000],
            confidence_score=_GEMINI_CONFIDENCE, extractor_name="gemini",
            extraction_method="gemini_grounding", crawled_at=now,
        )
        created += 1
    return created


def enrich_run_majors_from_gemini(run: PipelineRun, limit: int = 0, concurrency: int = 0,
                                  use_cache: bool = True, set_status: bool = True) -> dict:
    """For every staged university in the run, ask Gemini (grounded) for its list
    of majors and store them as ExtractedProgram rows (1-to-many). Progress is
    written to ``stats_json["gemini_majors"]`` for the live UI."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from .gemini_enrich import enrich_majors, is_configured

    if not is_configured():
        raise RuntimeError("No Gemini API key configured — set GEMINI_API_KEY / GEMINI_API_KEYS.")

    unis = list(run.universities.exclude(name="").order_by("name"))
    if limit:
        unis = unis[:limit]
    concurrency = concurrency or getattr(settings, "GEMINI_CONCURRENCY", 4)

    stats = {"attempted": 0, "with_majors": 0, "programs": 0, "errors": 0,
             "total": len(unis), "done": False}
    if set_status:
        run.status = PipelineRun.Status.CRAWLING
    run.stats_json = {**run.stats_json, "gemini_majors": dict(stats)}
    run.save(update_fields=["status", "stats_json", "updated_at"] if set_status
             else ["stats_json", "updated_at"])

    def _fetch(uni):
        return uni, enrich_majors(
            uni.name, uni.country or run.country_name, website=uni.website,
            city=uni.city, country_code=uni.country_code or run.country_code,
            use_cache=use_cache,
        )

    def _handle(uni, result):
        stats["attempted"] += 1
        if result.get("error"):
            stats["errors"] += 1
            logger.warning("gemini majors %s: %s", uni.name, result["error"])
        else:
            n = enrich_uni_majors_from_gemini(uni, result)
            stats["programs"] += n
            if n:
                stats["with_majors"] += 1
        run.stats_json = {**run.stats_json, "gemini_majors": dict(stats)}
        run.save(update_fields=["stats_json", "updated_at"])

    if concurrency > 1 and unis:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(_fetch, u) for u in unis]
            for fut in as_completed(futures):
                uni, result = fut.result()
                _handle(uni, result)
    else:
        for u in unis:
            uni, result = _fetch(u)
            _handle(uni, result)

    stats["done"] = True
    run.total_programs_found = run.programs.count()
    run.stats_json = {**run.stats_json, "gemini_majors": dict(stats)}
    run.save(update_fields=["total_programs_found", "stats_json", "updated_at"])
    logger.info("run %s gemini majors: %s", run.pk, stats)
    return stats


def enrich_run_from_wikipedia(
    run: PipelineRun, limit: int = 0, concurrency: int = 0, progress_callback=None,
) -> dict:
    """Stage English universities from Wikipedia for all valid seeds with an
    article. Articles are prefetched concurrently (network), then parsed/written
    serially. Run before crawl_run so official-site crawling has a website."""
    seeds = list(run.seeds.filter(status=InstitutionSeed.Status.VALID).exclude(wikipedia_url=""))
    if limit:
        seeds = seeds[:limit]

    concurrency = concurrency or getattr(settings, "ETL_WIKIPEDIA_CONCURRENCY", 6)
    htmls = {}
    if concurrency > 1 and seeds:
        from .fetch_pool import fetch_articles_html
        htmls = fetch_articles_html([s.wikipedia_url for s in seeds], max_workers=concurrency)

    stats = {"attempted": 0, "staged": 0, "total": len(seeds), "done": False}
    if progress_callback:
        progress_callback(processed=0, total=len(seeds))
    run.stats_json = {**run.stats_json, "wikipedia_enrich": dict(stats)}
    run.worker_heartbeat_at = timezone.now()
    run.save(update_fields=["stats_json", "worker_heartbeat_at", "updated_at"])
    for seed in seeds:
        stats["attempted"] += 1
        if enrich_from_wikipedia(run, seed, html=htmls.get(seed.wikipedia_url)) is not None:
            stats["staged"] += 1
        if progress_callback:
            progress_callback(
                processed=stats["attempted"],
                total=len(seeds),
                current_item=seed.name,
                current_url=seed.wikipedia_url,
                staged=stats["staged"],
            )
        if stats["attempted"] % 10 == 0:
            run.stats_json = {**run.stats_json, "wikipedia_enrich": dict(stats)}
            run.worker_heartbeat_at = timezone.now()
            run.save(update_fields=["stats_json", "worker_heartbeat_at", "updated_at"])
    stats["done"] = True
    run.stats_json = {**run.stats_json, "wikipedia_enrich": stats}
    run.worker_heartbeat_at = timezone.now()
    run.save(update_fields=["stats_json", "worker_heartbeat_at", "updated_at"])
    logger.info("run %s wikipedia enrich: %s", run.pk, stats)
    return stats
