"""Import approved staging records into the target universities app.

Rules:
- only approved records, or (without --approved-only) records whose
  confidence_score >= threshold AND validation_status is valid/warnings;
- never invalid, rejected, needs_review or non-higher-education records;
- upsert universities by external id > slug > website domain > name+location;
- upsert programs by (university, normalized program_name, degree_level);
- never overwrite a non-empty existing value with an empty one, and only
  overwrite with high-confidence data;
- dry-run writes ImportJob/ImportLog (would_create/would_update) but never
  touches the target tables.
"""

import logging

from django.db import transaction
from django.utils import timezone

from academic_etl.models import (
    HIGHER_ED_DEGREE_LEVELS,
    ExtractedProgram,
    ExtractedUniversity,
    ImportJob,
    ImportLog,
    PipelineRun,
    ReviewStatus,
    ValidationStatus,
)
from universities.models import Program, University

from .normalize import make_slug, normalize_program_name, url_domain

logger = logging.getLogger(__name__)

# staging field -> target field (identical names)
UNIVERSITY_FIELDS = [
    "name", "location", "description", "sponsored", "website", "global_rank",
    "financials", "student_loan_available", "campus_student_life",
    "number_of_students", "student_to_faculty_ratio", "international_student_ratio",
    "housing_availability", "admissions_contact", "admissions_phone",
    "contact_person", "admissions_page_link", "immigration_support",
    "university_campuses", "country", "country_code",
]
BOOL_TARGET_FIELDS = {"sponsored", "student_loan_available", "housing_availability", "immigration_support"}

PROGRAM_FIELDS = [
    "program_name", "degree_level", "field_of_study", "faculty_or_school",
    "description", "duration", "study_mode", "language", "tuition_fee",
    "currency", "program_url",
]

OVERWRITE_MIN_CONFIDENCE = 0.8


def _eligible(record, approved_only: bool, threshold: float) -> tuple[bool, str]:
    if record.review_status == ReviewStatus.REJECTED:
        return False, "rejected by reviewer"
    if record.validation_status in (ValidationStatus.INVALID,):
        return False, "validation status invalid"
    if record.review_status in (ReviewStatus.APPROVED, ReviewStatus.EDITED):
        return True, "approved"
    if approved_only:
        return False, "not approved (approved-only mode)"
    if record.validation_status == ValidationStatus.NEEDS_REVIEW:
        return False, "needs_review is never auto-imported"
    if record.confidence_score >= threshold and record.validation_status in (
        ValidationStatus.VALID, ValidationStatus.WARNINGS,
    ):
        return True, f"confidence {record.confidence_score} >= {threshold}"
    return False, f"confidence {record.confidence_score} < {threshold}"


def _match_university(uni: ExtractedUniversity):
    """Return (existing University | None, matched_by)."""
    if uni.external_id and uni.external_id.isdigit():
        existing = University.objects.filter(pk=int(uni.external_id)).first()
        if existing:
            return existing, "id"
    if uni.slug:
        existing = University.objects.filter(slug=uni.slug).first()
        if existing:
            return existing, "slug"
    domain = url_domain(uni.website)
    if domain:
        for candidate in University.objects.exclude(website=""):
            if url_domain(candidate.website) == domain:
                return candidate, "website_domain"
    if uni.name:
        existing = University.objects.filter(
            name__iexact=uni.name.strip(), location__iexact=uni.location.strip()
        ).first()
        if existing:
            return existing, "name_location"
    return None, ""


def _diff_university(existing: University | None, uni: ExtractedUniversity) -> dict:
    """Compute field changes the import would apply. Protects good existing data."""
    diff = {}
    for field in UNIVERSITY_FIELDS:
        new = False if field == "sponsored" else getattr(uni, field)
        if new in ("", None):
            continue  # never push empty over anything
        if field in BOOL_TARGET_FIELDS and new is None:
            continue
        old = getattr(existing, field) if existing else None
        if existing is not None and old not in ("", None, False) and field != "sponsored":
            if old == new:
                continue
            # only overwrite real existing data with high-confidence values
            if uni.confidence_score < OVERWRITE_MIN_CONFIDENCE:
                continue
        if old != new:
            diff[field] = {"old": old if existing else None, "new": new}
    return diff


def import_run(run: PipelineRun, dry_run: bool = True, approved_only: bool = True,
               threshold: float = 0.75) -> ImportJob:
    job = ImportJob.objects.create(
        pipeline_run=run, dry_run=dry_run, approved_only=approved_only,
        confidence_threshold=threshold, status=ImportJob.Status.RUNNING,
    )
    try:
        with transaction.atomic():
            _import_universities(job, run)
        job.status = ImportJob.Status.COMPLETED
    except Exception as exc:
        job.status = ImportJob.Status.FAILED
        job.error_message = str(exc)[:2000]
        logger.exception("import job %s failed", job.pk)
    job.finished_at = timezone.now()
    job.save()
    logger.info(
        "import job %s (%s): processed=%s created=%s updated=%s skipped=%s",
        job.pk, "dry-run" if dry_run else "LIVE", job.total_processed,
        job.total_created, job.total_updated, job.total_skipped,
    )
    return job


def _log(job, entity_type, entity_id, action, matched_by="", diff=None, message="", target_id=None):
    ImportLog.objects.create(
        import_job=job, entity_type=entity_type, entity_id=entity_id,
        action=action, matched_by=matched_by, diff_json=diff or {},
        message=message, target_id=target_id,
    )


def _import_universities(job: ImportJob, run: PipelineRun):
    for uni in run.universities.all().order_by("pk"):
        job.total_processed += 1
        ok, reason = _eligible(uni, job.approved_only, job.confidence_threshold)
        if not ok:
            job.total_skipped += 1
            _log(job, "university", uni.pk, ImportLog.Action.SKIP, message=reason)
            continue
        if not uni.name.strip():
            job.total_skipped += 1
            _log(job, "university", uni.pk, ImportLog.Action.SKIP, message="missing name")
            continue

        existing, matched_by = _match_university(uni)
        diff = _diff_university(existing, uni)

        if existing is None:
            slug = uni.slug or make_slug(uni.name, uni.city)
            if job.dry_run:
                job.total_created += 1
                _log(job, "university", uni.pk, ImportLog.Action.WOULD_CREATE,
                     diff=diff, message=f"would create with slug {slug!r}")
                target = None
            else:
                target = University(slug=slug)
                for field, change in diff.items():
                    setattr(target, field, change["new"])
                for bf in BOOL_TARGET_FIELDS:
                    if getattr(target, bf, None) is None:
                        setattr(target, bf, False)
                target.save()
                job.total_created += 1
                _log(job, "university", uni.pk, ImportLog.Action.CREATE,
                     diff=diff, target_id=target.pk)
        else:
            if not diff:
                job.total_skipped += 1
                _log(job, "university", uni.pk, ImportLog.Action.SKIP, matched_by=matched_by,
                     target_id=existing.pk, message="no changes (existing data kept)")
                target = existing
            elif job.dry_run:
                job.total_updated += 1
                _log(job, "university", uni.pk, ImportLog.Action.WOULD_UPDATE,
                     matched_by=matched_by, diff=diff, target_id=existing.pk)
                target = existing
            else:
                for field, change in diff.items():
                    setattr(existing, field, change["new"])
                existing.save()
                job.total_updated += 1
                _log(job, "university", uni.pk, ImportLog.Action.UPDATE,
                     matched_by=matched_by, diff=diff, target_id=existing.pk)
                target = existing

        _import_programs(job, uni, target)
    job.save()


def _import_programs(job: ImportJob, uni: ExtractedUniversity, target: University | None):
    for program in uni.programs.all().order_by("pk"):
        job.total_processed += 1
        ok, reason = _eligible(program, job.approved_only, job.confidence_threshold)
        if ok and program.degree_level not in HIGHER_ED_DEGREE_LEVELS:
            ok, reason = False, f"degree_level {program.degree_level!r} is not higher education"
        if ok and program.is_higher_education_program is not True \
                and program.review_status not in (ReviewStatus.APPROVED, ReviewStatus.EDITED):
            ok, reason = False, "higher-education flag uncertain; needs review"
        if not ok:
            job.total_skipped += 1
            _log(job, "program", program.pk, ImportLog.Action.SKIP, message=reason)
            continue

        norm_name = normalize_program_name(program.program_name)
        existing = None
        if target is not None:
            for candidate in target.programs.filter(degree_level=program.degree_level):
                if normalize_program_name(candidate.program_name) == norm_name:
                    existing = candidate
                    break

        diff = {}
        for field in PROGRAM_FIELDS:
            new = getattr(program, field)
            if new in ("", None):
                continue
            old = getattr(existing, field) if existing else None
            if existing is not None and old not in ("", None) and old != new \
                    and program.confidence_score < OVERWRITE_MIN_CONFIDENCE:
                continue
            if old != new:
                diff[field] = {"old": old if existing else None, "new": new}

        if existing is None:
            if job.dry_run or target is None:
                job.total_created += 1
                _log(job, "program", program.pk, ImportLog.Action.WOULD_CREATE, diff=diff,
                     message="would create" + ("" if target else " (university also pending creation)"))
            else:
                obj = Program(university=target)
                for field, change in diff.items():
                    setattr(obj, field, change["new"])
                obj.save()
                job.total_created += 1
                _log(job, "program", program.pk, ImportLog.Action.CREATE, diff=diff, target_id=obj.pk)
        else:
            if not diff:
                job.total_skipped += 1
                _log(job, "program", program.pk, ImportLog.Action.SKIP,
                     matched_by="university+name+level", target_id=existing.pk, message="no changes")
            elif job.dry_run:
                job.total_updated += 1
                _log(job, "program", program.pk, ImportLog.Action.WOULD_UPDATE,
                     matched_by="university+name+level", diff=diff, target_id=existing.pk)
            else:
                for field, change in diff.items():
                    setattr(existing, field, change["new"])
                existing.save()
                job.total_updated += 1
                _log(job, "program", program.pk, ImportLog.Action.UPDATE,
                     matched_by="university+name+level", diff=diff, target_id=existing.pk)
