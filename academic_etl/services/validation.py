"""Validation + scoring for staged universities and programs."""

import logging
import re

from academic_etl.models import (
    HIGHER_ED_DEGREE_LEVELS,
    DegreeLevel,
    ExtractedProgram,
    ExtractedUniversity,
    PipelineRun,
    ValidationIssue,
    ValidationStatus,
)

from .lang import is_english
from .financial import is_canonical_financials
from .normalize import EMAIL_RE, is_valid_phone, normalize_program_name, normalize_url, url_domain

logger = logging.getLogger(__name__)

CRITICAL_FIELDS = {"name", "website", "description", "location"}
IMPORTANT_FIELDS = {"financials", "number_of_students", "campus_student_life"}
OPTIONAL_FIELDS = {
    "contact_person", "immigration_support", "housing_availability",
    "university_campuses", "student_loan_available", "sponsored",
}

COMPLETENESS_FIELDS = list(CRITICAL_FIELDS | IMPORTANT_FIELDS | {"slug"})

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_STRIP_ARTICLES = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def _normalize_name_for_dedup(name: str) -> str:
    """Normalize a university name for deduplication comparison."""
    n = (name or "").strip().lower()
    n = _STRIP_ARTICLES.sub("", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def validate_run(run: PipelineRun) -> dict:
    run.status = PipelineRun.Status.VALIDATING
    run.save(update_fields=["status", "updated_at"])
    # re-validate from scratch
    ValidationIssue.objects.filter(pipeline_run=run).delete()

    stats = {"universities": {"valid": 0, "warnings": 0, "invalid": 0, "needs_review": 0},
             "programs": {"valid": 0, "warnings": 0, "invalid": 0, "needs_review": 0}}

    seen_domains, seen_slugs, seen_name_loc = {}, {}, {}
    for uni in run.universities.all().order_by("pk"):
        status = _validate_university(run, uni, seen_domains, seen_slugs, seen_name_loc)
        stats["universities"][status] += 1

    seen_programs = {}
    for program in run.programs.select_related("extracted_university").order_by("pk"):
        status = _validate_program(run, program, seen_programs)
        stats["programs"][status] += 1

    run.stats_json = {**run.stats_json, "validation": stats}
    run.status = PipelineRun.Status.REVIEW
    run.save()
    logger.info("run %s validated: %s", run.pk, stats)
    return stats


def _issue(run, entity_type, entity_id, field, severity, code, message):
    ValidationIssue.objects.create(
        pipeline_run=run, entity_type=entity_type, entity_id=entity_id,
        field_name=field, severity=severity, code=code, message=message,
    )


def _validate_university(run, uni: ExtractedUniversity, seen_domains, seen_slugs, seen_name_loc) -> str:
    from academic_etl.models import ReviewStatus
    uni.review_status = ReviewStatus.PENDING
    errors, warnings = 0, 0

    def err(field, code, message):
        nonlocal errors
        errors += 1
        _issue(run, "university", uni.pk, field, ValidationIssue.Severity.ERROR, code, message)

    def warn(field, code, message):
        nonlocal warnings
        warnings += 1
        _issue(run, "university", uni.pk, field, ValidationIssue.Severity.WARNING, code, message)

    if not uni.name.strip():
        err("name", "missing_name", "University name is required.")

    website = normalize_url(uni.website)
    if uni.website and not website:
        err("website", "invalid_website", f"Website is not a valid URL: {uni.website!r}")
    elif not uni.website:
        warn("website", "missing_website", "No website; institution cannot be crawled or deduped by domain.")

    if not uni.slug:
        warn("slug", "missing_slug", "Slug missing; it will be generated at import time.")
    elif not SLUG_RE.match(uni.slug):
        err("slug", "invalid_slug", f"Slug is not URL-safe: {uni.slug!r}")

    if uni.admissions_contact and not EMAIL_RE.fullmatch(uni.admissions_contact.strip()):
        warn("admissions_contact", "invalid_email", f"Not a valid email: {uni.admissions_contact!r}")
    if uni.admissions_phone and not is_valid_phone(uni.admissions_phone):
        warn("admissions_phone", "invalid_phone",
             f"Phone is not a canonical E.164 value: {uni.admissions_phone!r}")
    if uni.admissions_page_link and not normalize_url(uni.admissions_page_link):
        warn("admissions_page_link", "invalid_url", "Admissions page link is not a valid URL.")
    if uni.number_of_students is not None and uni.number_of_students > 2_000_000:
        warn("number_of_students", "implausible_number", f"{uni.number_of_students} students is implausible.")
    if uni.financials and not is_canonical_financials(uni.financials, uni.country_code):
        warn(
            "financials",
            "invalid_financials_format",
            "Financials must be formatted like 'INR 50k-200k ($600-2400)'.",
        )

    # --- Smart dedup with city disambiguation ---
    domain = url_domain(uni.website)
    city = (uni.city or "").strip().lower()
    norm_name = _normalize_name_for_dedup(uni.name)

    # Rule 1: Same website domain = always duplicate
    if domain:
        if domain in seen_domains:
            err("website", "duplicate_domain",
                 f"Same domain as ExtractedUniversity #{seen_domains[domain]} ({domain}).")
        else:
            seen_domains[domain] = uni.pk

    if uni.slug:
        if uni.slug in seen_slugs:
            err("slug", "duplicate_slug", f"Same slug as ExtractedUniversity #{seen_slugs[uni.slug]}.")
        else:
            seen_slugs[uni.slug] = uni.pk

    # Rule 2-4: Name + city dedup
    name_city_key = (norm_name, city)
    if norm_name:
        if name_city_key in seen_name_loc:
            # Same name + same city = duplicate
            err("name", "duplicate_name_city",
                 f"Same name+city as ExtractedUniversity #{seen_name_loc[name_city_key]}.")
        else:
            # Check if same name exists in a DIFFERENT city (keep both, log info)
            existing = [(c, pk) for (n, c), pk in seen_name_loc.items() if n == norm_name and c != city]
            if existing:
                other_city, other_pk = existing[0]
                _issue(run, "university", uni.pk, "name", "info", "same_name_different_city",
                       f"Same name as #{other_pk} but different city ({other_city} vs {city}). Both kept.")
            seen_name_loc[name_city_key] = uni.pk

    # cross-source conflicts (KB seed value disagrees with the official website)
    source_conflicts = (uni.normalized_json or {}).get("source_conflicts") or []
    for field in source_conflicts:
        warn(field, "source_conflict",
             "Wikidata/Wikipedia value conflicts with the official website; needs review.")

    # English-only catalog: flag non-English description (names can be
    # transliterated from Hindi/Sanskrit/etc. and that's fine)
    non_english = False
    desc = uni.description or ""
    if desc and not is_english(desc):
        non_english = True
        warn("description", "non_english", "University description is not in English.")

    # scores — only count CRITICAL + IMPORTANT fields (not optional)
    filled = sum(1 for f in COMPLETENESS_FIELDS if getattr(uni, f) not in ("", None))
    uni.completeness_score = round(filled / len(COMPLETENESS_FIELDS), 2)
    base_conf = uni.confidence_score or 0.5
    uni.confidence_score = round(
        max(0.0, min(1.0, base_conf - 0.25 * errors - 0.05 * warnings + 0.1 * uni.completeness_score)), 2
    )

    # Auto-fill location from country/city if empty
    if not uni.location and (uni.country or uni.city):
        uni.location = ", ".join(filter(None, [uni.city, uni.country]))

    # Check if critical fields are all present
    critical_filled = all(getattr(uni, f) not in ("", None) for f in CRITICAL_FIELDS)

    if errors:
        uni.validation_status = ValidationStatus.INVALID
    elif source_conflicts or non_english:
        uni.validation_status = ValidationStatus.NEEDS_REVIEW
    elif not critical_filled:
        uni.validation_status = ValidationStatus.NEEDS_REVIEW
    elif warnings:
        uni.validation_status = ValidationStatus.WARNINGS
    else:
        uni.validation_status = ValidationStatus.VALID

    # AUTO-APPROVE: if critical fields filled + no errors + confidence >= 0.5
    if uni.validation_status in (ValidationStatus.VALID, ValidationStatus.WARNINGS):
        if critical_filled and uni.confidence_score >= 0.5:
            uni.review_status = ReviewStatus.APPROVED

    uni.save(update_fields=[
        "completeness_score", "confidence_score", "validation_status",
        "review_status", "updated_at",
    ])
    return uni.validation_status


def _validate_program(run, program: ExtractedProgram, seen_programs) -> str:
    errors, warnings = 0, 0

    def err(field, code, message):
        nonlocal errors
        errors += 1
        _issue(run, "program", program.pk, field, ValidationIssue.Severity.ERROR, code, message)

    def warn(field, code, message):
        nonlocal warnings
        warnings += 1
        _issue(run, "program", program.pk, field, ValidationIssue.Severity.WARNING, code, message)

    if not program.program_name.strip():
        err("program_name", "missing_program_name", "Program name is required.")

    valid_levels = {choice[0] for choice in DegreeLevel.choices}
    if program.degree_level not in valid_levels:
        err("degree_level", "invalid_degree_level", f"Unknown degree level: {program.degree_level!r}")

    needs_review = False
    if program.degree_level == DegreeLevel.UNKNOWN or program.is_higher_education_program is None:
        needs_review = True
        warn("degree_level", "uncertain_degree_level",
             "Could not confidently classify degree level; review required.")
    elif program.degree_level not in HIGHER_ED_DEGREE_LEVELS:
        warn("degree_level", "non_higher_education",
             "Not a higher-education program; it will never be auto-imported.")

    for field in ("program_url", "source_url"):
        value = getattr(program, field)
        if value and not normalize_url(value):
            warn(field, "invalid_url", f"{field} is not a valid URL.")
    if not program.program_url and not program.source_url:
        warn("source_url", "missing_provenance",
             "Program has neither a program_url nor a source_url; provenance is missing.")

    if program.program_name and not is_english(program.program_name):
        needs_review = True
        warn("program_name", "non_english", "Program name is not in English.")

    key = (program.extracted_university_id, normalize_program_name(program.program_name), program.degree_level)
    if key in seen_programs:
        warn("program_name", "duplicate_program",
             f"Duplicate of ExtractedProgram #{seen_programs[key]} (same university+name+level).")
    else:
        seen_programs[key] = program.pk

    program.confidence_score = round(
        max(0.0, min(1.0, (program.confidence_score or 0.5) - 0.25 * errors - 0.05 * warnings)), 2
    )
    if errors:
        program.validation_status = ValidationStatus.INVALID
    elif needs_review:
        program.validation_status = ValidationStatus.NEEDS_REVIEW
    elif warnings:
        program.validation_status = ValidationStatus.WARNINGS
    else:
        program.validation_status = ValidationStatus.VALID
    program.save(update_fields=["confidence_score", "validation_status", "updated_at"])
    return program.validation_status
