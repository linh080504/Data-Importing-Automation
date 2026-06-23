"""Review web UI for the ETL pipeline (plain Django templates)."""

import csv
import json
import logging
import re
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from universities.models import Program, University

from .models import (
    CountryConfig,
    CrawlSchedule,
    DataResetJob,
    DegreeLevel,
    ExtractedProgram,
    ExtractedSpecialization,
    ExtractedUniversity,
    FieldEvidence,
    ImportJob,
    InstitutionSeed,
    PipelineRun,
    ReviewStatus,
    ValidationStatus,
    ValidationIssue,
)
from .services.crawler import SiteCrawler
from .services.discovery import resolve_country, run_discovery
from .services.exporter import major_rows, simple_major_rows, university_rows
from .services.importer import _diff_university, _eligible, _match_university, import_run
from .services.normalize import (
    make_slug,
    normalize_bool,
    normalize_email,
    normalize_int,
    normalize_phone,
    normalize_url,
)
from .services.gemini_enrich import is_configured as gemini_is_configured
from .services.pipeline import (
    crawl_run,
    enrich_run_from_gemini,
    enrich_run_majors_from_gemini,
    enrich_run_from_wikipedia,
)
from .services.unified_worker import launch_unified_worker
from .services.pipeline_execution import (
    LOCK_POLL_SECONDS,
    PIPELINE_STAGES,
    PipelineHostLock,
    PipelineCancelled,
    PipelineLeaseLost,
    begin_stage,
    claim_pipeline_run,
    claim_stale_pipeline_runs,
    check_cancelled,
    complete_stage,
    heartbeat,
    is_recoverable_error,
    mark_complete,
    mark_cancelled,
    mark_failed,
    mark_retrying,
    owns_pipeline_run,
    release_worker,
    update_stage_progress,
)
from .services.validation import validate_run

# CSV-shaped university fields shown in tables/forms, in display order.
UNIVERSITY_CSV_FIELDS = [
    "name", "location", "description", "slug", "sponsored", "website",
    "global_rank", "financials", "student_loan_available", "campus_student_life",
    "number_of_students", "student_to_faculty_ratio", "international_student_ratio",
    "housing_availability", "admissions_contact", "admissions_phone",
    "contact_person", "admissions_page_link", "immigration_support",
    "university_campuses",
]
UNIVERSITY_REVIEW_FIELDS = UNIVERSITY_CSV_FIELDS + ["country", "country_code"]
UNIVERSITY_BOOL_FIELDS = {
    "sponsored", "student_loan_available", "housing_availability", "immigration_support",
}
UNIVERSITY_INT_FIELDS = {"number_of_students", "university_campuses"}
UNIVERSITY_URL_FIELDS = {"website", "admissions_page_link"}
UNIVERSITY_SORTS = {
    "name": ("name",),
    "confidence": ("-confidence_score", "name"),
    "completeness": ("-completeness_score", "name"),
    "validation": ("validation_status", "name"),
    "review": ("review_status", "name"),
    "updated": ("-updated_at", "name"),
}

MAJOR_REVIEW_FIELDS = [
    "program_name", "degree_level", "field_of_study", "faculty_or_school", "description",
    "duration", "study_mode", "language", "tuition_fee", "currency", "intake",
    "application_deadline", "admission_requirements", "career_outcomes", "accreditation",
    "program_url", "source_url", "campus",
]
PROGRAM_REVIEW_FIELDS = MAJOR_REVIEW_FIELDS
MAJOR_SORTS = {
    "university": ("extracted_university__name", "program_name"),
    "major": ("program_name",),
    "level": ("degree_level", "program_name"),
    "confidence": ("-confidence_score", "program_name"),
    "validation": ("validation_status", "program_name"),
    "review": ("review_status", "program_name"),
    "updated": ("-updated_at", "program_name"),
}

CLEAN_REVIEW_STATUSES = [ReviewStatus.APPROVED, ReviewStatus.EDITED]
CLEAN_VALIDATION_STATUSES = [ValidationStatus.VALID, ValidationStatus.WARNINGS]
DEFAULT_REQUIRED_UNIVERSITY_EXPORT_FIELDS = (
    "name", "location", "description", "slug", "website",
    "financials", "campus_student_life", "number_of_students",
)


def _required_university_export_fields():
    return tuple(
        getattr(settings, "ETL_REQUIRED_UNIVERSITY_EXPORT_FIELDS",
                DEFAULT_REQUIRED_UNIVERSITY_EXPORT_FIELDS)
    )


def _get_country_options():
    from academic_etl.services.country_registry import get_all_country_options
    return get_all_country_options()


def _ratio(count: int, total: int) -> int:
    if total <= 0:
        return 0
    return round((count / total) * 100)


def _recover_stale_pipeline_runs():
    """Relaunch stale local workers while preserving their checkpoints."""
    logger = logging.getLogger("academic_etl.pipeline")
    for run_id, token in claim_stale_pipeline_runs():
        try:
            launch_unified_worker(run_id, token)
            logger.warning("Recovered stale pipeline run #%d", run_id)
        except OSError as exc:
            logger.error("Could not recover pipeline run #%d: %s", run_id, exc)
            mark_failed(run_id, token, exc)


def _distribution(qs, field: str, choices=None) -> list[dict]:
    total = qs.count()
    raw = {row[field]: row["n"] for row in qs.values(field).annotate(n=Count("pk"))}
    keys = [choice[0] for choice in choices] if choices else sorted(raw)
    return [
        {"label": key or "empty", "count": raw.get(key, 0), "pct": _ratio(raw.get(key, 0), total)}
        for key in keys
    ]


def _dashboard_funnel() -> list[dict]:
    clean_unis = _clean_university_qs(ExtractedUniversity.objects.all()).count()
    clean_majors = _clean_major_qs(ExtractedProgram.objects.all()).count()
    values = [
        ("Discovered", InstitutionSeed.objects.count()),
        ("Crawled", InstitutionSeed.objects.filter(status=InstitutionSeed.Status.CRAWLED).count()),
        ("Universities", ExtractedUniversity.objects.count()),
        ("Majors", ExtractedProgram.objects.count()),
        ("Clean data", clean_unis + clean_majors),
    ]
    max_value = max([value for _, value in values] + [1])
    return [{"label": label, "value": value, "pct": _ratio(value, max_value)} for label, value in values]


def _run_progress(run: PipelineRun) -> dict:
    seed_counts = {
        row["status"]: row["n"]
        for row in run.seeds.values("status").annotate(n=Count("pk"))
    }
    total_seeds = sum(seed_counts.values())
    ready_to_crawl = seed_counts.get(InstitutionSeed.Status.VALID, 0)
    discovered = seed_counts.get(InstitutionSeed.Status.DISCOVERED, 0)
    crawled = seed_counts.get(InstitutionSeed.Status.CRAWLED, 0)
    failed = seed_counts.get(InstitutionSeed.Status.CRAWL_FAILED, 0)
    skipped = seed_counts.get(InstitutionSeed.Status.SKIPPED, 0)
    invalid = seed_counts.get(InstitutionSeed.Status.INVALID, 0)
    needs_review_seed = seed_counts.get(InstitutionSeed.Status.NEEDS_REVIEW, 0)
    done_seeds = crawled + failed + skipped + invalid + needs_review_seed
    pending_seeds = ready_to_crawl + discovered

    universities = run.universities.count()
    majors = run.programs.count()
    pages = run.pages.count()
    issues = run.issues.count()
    clean_universities = _clean_university_qs(run.universities.all()).count()
    clean_majors = _clean_major_qs(run.programs.all()).count()
    not_validated = (
        run.universities.filter(validation_status=ValidationStatus.NOT_VALIDATED).count()
        + run.programs.filter(validation_status=ValidationStatus.NOT_VALIDATED).count()
    )
    review_pending = (
        run.universities.filter(review_status=ReviewStatus.PENDING).count()
        + run.programs.filter(review_status=ReviewStatus.PENDING).count()
    )

    active_statuses = {
        PipelineRun.Status.QUEUED,
        PipelineRun.Status.DISCOVERING,
        PipelineRun.Status.CRAWLING,
        PipelineRun.Status.RETRYING,
        PipelineRun.Status.CANCELLING,
        PipelineRun.Status.VALIDATING,
        PipelineRun.Status.IMPORTING,
    }
    is_active = run.status in active_statuses
    has_staging = universities + majors > 0

    # Gemini grounded enrichment progress (a Gemini run keeps seeds in `valid`,
    # so seed-based progress doesn't apply — track attempted/total instead).
    is_gemini = run.crawl_scope == "gemini_grounding"
    sj = run.stats_json or {}
    gem = sj.get("gemini_enrich") or {}
    gem_majors = sj.get("gemini_majors") or {}
    wikipedia_enrich = sj.get("wikipedia_enrich") or {}
    web_scrape = sj.get("web_scrape") or {}
    programs_crawl = sj.get("programs_crawl") or {}
    gem_total = gem.get("total", 0)
    gem_attempted = gem.get("attempted", 0)
    active = run.status == PipelineRun.Status.CRAWLING
    current_step = sj.get("current_step", "")
    is_complete = current_step == "Complete"
    execution_state = run.execution_state or {}
    stage_progress = execution_state.get("stage_progress") or {}
    active_stage = execution_state.get("current_stage", "")
    completed_stages = execution_state.get("completed_stages") or []
    stage_processed = int(stage_progress.get("processed") or 0)
    stage_total = int(stage_progress.get("total") or 0)
    stage_fraction = min(stage_processed / stage_total, 1) if stage_total else 0
    stage_index = PIPELINE_STAGES.index(active_stage) if active_stage in PIPELINE_STAGES else -1
    stage_number = stage_index + 1 if stage_index >= 0 else 0
    pipeline_progress_pct = (
        100
        if is_complete
        else round(((len(completed_stages) + stage_fraction) / len(PIPELINE_STAGES)) * 100)
        if active_stage in PIPELINE_STAGES
        else 0
    )
    is_untracked_legacy = bool(
        is_active
        and not run.worker_token
        and not run.worker_heartbeat_at
        and not execution_state.get("version")
        and not any((wikipedia_enrich, web_scrape, programs_crawl, gem, gem_majors))
    )
    execution_mode = (
        (run.crawl_scope or "").removeprefix("unified_")
        if (run.crawl_scope or "").startswith("unified_")
        else run.crawl_mode
    ) or "fast"
    eligible_seeds = ready_to_crawl + crawled + failed + skipped
    staged_seeds = run.universities.exclude(seed__isnull=True).values("seed_id").distinct().count()
    unresolved_seeds = max(eligible_seeds - staged_seeds, 0)
    terminal_seeds = crawled + failed + skipped
    if execution_mode == "thorough":
        coverage_detail = (
            f"Official crawl: {terminal_seeds}/{eligible_seeds} terminal "
            f"({crawled} crawled, {failed} failed, {skipped} skipped)."
        )
        coverage_pct = _ratio(terminal_seeds, eligible_seeds)
    else:
        coverage_detail = (
            f"Staging coverage: {staged_seeds}/{eligible_seeds} resolved; "
            f"{unresolved_seeds} unresolved."
        )
        coverage_pct = _ratio(staged_seeds, eligible_seeds)
    stale_cutoff = timezone.now() - timedelta(
        seconds=getattr(settings, "ETL_WORKER_STALE_SECONDS", 90)
    )
    is_stale = bool(
        is_active
        and run.worker_heartbeat_at
        and run.worker_heartbeat_at < stale_cutoff
    )
    wikipedia_running = (
        active and current_step.startswith("Step 1/")
        and bool(wikipedia_enrich.get("total")) and not wikipedia_enrich.get("done")
    )
    web_scrape_running = (
        active and current_step.startswith("Step 2/")
        and bool(web_scrape.get("total")) and not web_scrape.get("done")
    )
    fields_running = is_gemini and active and bool(gem) and not gem.get("done")
    majors_running = is_gemini and active and bool(gem_majors) and not gem_majors.get("done")
    programs_crawl_running = active and bool(programs_crawl.get("total")) and not programs_crawl.get("done")
    gem_running = fields_running or majors_running
    if majors_running:
        gem_pct = _ratio(gem_majors.get("attempted", 0), gem_majors.get("total", 0))
    else:
        gem_pct = _ratio(gem_attempted, gem_total)

    if is_complete:
        phase_label = "COMPLETE"
        phase_detail = f"Pipeline finished. {coverage_detail}"
        tone = "ok"
    elif run.status == PipelineRun.Status.CANCELLING:
        phase_label = "CANCELLING"
        phase_detail = "Cancellation requested. Waiting for the worker to release the pipeline lock."
        tone = "warn"
    elif run.status == PipelineRun.Status.CANCELLED:
        phase_label = "CANCELLED"
        phase_detail = "Pipeline stopped before completion."
        tone = "muted"
    elif is_untracked_legacy:
        phase_label = "UNTRACKED LEGACY WORKER"
        phase_detail = "This run has no worker token or heartbeat. It will not be auto-restarted."
        tone = "bad"
    elif majors_running:
        phase_label = "ĐANG LẤY MAJOR (GEMINI)"
        phase_detail = (f"Đã xử lý {gem_majors.get('attempted', 0)}/{gem_majors.get('total', 0)} trường, "
                        f"thu {gem_majors.get('programs', 0)} ngành. Trang tự refresh.")
        tone = "warn"
    elif wikipedia_running:
        phase_label = "WIKIPEDIA ENRICH"
        phase_detail = (f"Processed {wikipedia_enrich.get('attempted', 0)}/{wikipedia_enrich.get('total', 0)} "
                        f"institutions; staged {wikipedia_enrich.get('staged', 0)}.")
        tone = "warn"
    elif web_scrape_running:
        phase_label = "WEB SCRAPE"
        phase_detail = (f"Processed {web_scrape.get('processed', 0)}/{web_scrape.get('total', 0)} "
                        f"institutions; enriched {web_scrape.get('enriched', 0)}.")
        tone = "warn"
    elif programs_crawl_running:
        phase_label = "ĐANG LẤY MAJOR"
        phase_detail = (f"Đã xử lý {programs_crawl.get('processed', 0)}/{programs_crawl.get('total', 0)} trường, "
                        f"thu {programs_crawl.get('programs', 0)} ngành. Trang tự refresh.")
        tone = "warn"
    elif fields_running:
        phase_label = "ĐANG GỌI GEMINI"
        phase_detail = (f"Đã xử lý {gem_attempted}/{gem_total} trường "
                        f"({gem.get('staged', 0)} có data, {gem.get('errors', 0)} lỗi/hết quota). "
                        f"Trang tự refresh.")
        tone = "warn"
    elif run.status == PipelineRun.Status.RETRYING:
        phase_label = "RETRYING"
        phase_detail = (
            f"Temporary failure; retry {run.retry_count}/3 is scheduled. "
            f"Checkpoint: {(run.execution_state or {}).get('current_stage', 'unknown')}."
        )
        tone = "warn"
    elif run.status == PipelineRun.Status.QUEUED:
        phase_label = "QUEUED"
        phase_detail = "Waiting for the single SQLite pipeline worker."
        tone = "info"
    elif run.status == PipelineRun.Status.FAILED:
        phase_label = "FAILED"
        phase_detail = "Job lỗi. Xem error message/log trước khi chạy tiếp."
        tone = "bad"
    elif run.status == PipelineRun.Status.DISCOVERING:
        phase_label = "DISCOVERRING"
        phase_detail = "Looking for school seeds by country."
        tone = "warn"
    elif run.status == PipelineRun.Status.CRAWLING:
        phase_label = f"STAGE {stage_number}/{len(PIPELINE_STAGES)}" if stage_number else "CRAWLING"
        phase_detail = (
            f"Processed {stage_processed}/{stage_total}. Latest: "
            f"{stage_progress.get('current_item') or 'waiting for activity'}."
        )
        tone = "warn"
    elif run.status == PipelineRun.Status.VALIDATING:
        phase_label = "ĐANG VALIDATE"
        phase_detail = "Đang kiểm tra chất lượng dữ liệu staging."
        tone = "warn"
    elif run.status == PipelineRun.Status.IMPORTING:
        phase_label = "ĐANG IMPORT"
        phase_detail = "Đang import dữ liệu đã approve vào bảng live."
        tone = "warn"
    elif is_gemini:
        # Gemini runs don't crawl — the right action for unfinished seeds is to
        # resume Gemini, so use Gemini-centric messaging (never "crawl").
        gem_remaining = max((ready_to_crawl + crawled) - universities, 0)
        if universities == 0:
            phase_label = "CHƯA CÓ DATA"
            phase_detail = "Chưa có trường nào. Bấm 'Run / resume AI gap-fill' để bắt đầu."
            tone = "info"
        elif gem_remaining > 0:
            phase_label = "GEMINI MỘT PHẦN"
            phase_detail = (f"Còn {gem_remaining}/{ready_to_crawl + crawled} trường chưa được "
                            f"Gemini điền (thường do hết quota ngày / key hết hạn). "
                            f"Bấm 'Run / resume AI gap-fill' để lấy tiếp — trường đã xong được cache, không tốn lại.")
            tone = "warn"
        elif not_validated > 0:
            phase_label = "CẦN VALIDATE"
            phase_detail = "Đã có data Gemini. Bấm 'Validate run' rồi 'Approve all valid'."
            tone = "info"
        elif clean_universities + clean_majors > 0:
            phase_label = "CÓ CLEAN DATA"
            phase_detail = "Đã đủ điều kiện export. Tải Universities CSV / Majors CSV (simple 3-col)."
            tone = "ok"
        elif review_pending > 0:
            phase_label = "CẦN APPROVE"
            phase_detail = "Data đã validate. Bấm 'Approve all valid' để vào Clean Data / CSV."
            tone = "info"
        else:
            phase_label = "ĐANG REVIEW"
            phase_detail = "Mở University/Major table để review dữ liệu."
            tone = "info"
    elif total_seeds == 0:
        phase_label = "CHƯA CÓ SEED"
        phase_detail = "Run chưa discover được seed nào."
        tone = "muted"
    elif ready_to_crawl > 0 and not has_staging:
        phase_label = "ĐÃ DISCOVER - CHƯA CRAWL"
        phase_detail = "Đã có seed hợp lệ. Bấm Continue crawl để lấy dữ liệu thật."
        tone = "info"
    elif ready_to_crawl > 0:
        phase_label = "CRAWL MỘT PHẦN"
        phase_detail = f"Còn {ready_to_crawl} seed hợp lệ chưa crawl. Có thể crawl tiếp để tăng coverage."
        tone = "warn"
    elif not_validated > 0:
        phase_label = "CRAWL XONG - CẦN VALIDATE"
        phase_detail = "Đã có staging data. Bấm Validate run để phân loại valid/warnings/invalid."
        tone = "info"
    elif review_pending > 0 and clean_universities + clean_majors == 0:
        phase_label = "CẦN HUMAN REVIEW"
        phase_detail = "Dữ liệu đã validate nhưng chưa approve, nên Clean Data còn trống."
        tone = "info"
    elif clean_universities + clean_majors > 0:
        phase_label = "CÓ CLEAN DATA"
        phase_detail = "Đã có record approved/edited đủ điều kiện export hoặc import."
        tone = "ok"
    elif run.status == PipelineRun.Status.COMPLETED:
        phase_label = "HOÀN TẤT"
        phase_detail = "Pipeline đã hoàn tất."
        tone = "ok"
    else:
        phase_label = "ĐANG REVIEW"
        phase_detail = "Mở University/Major table để review dữ liệu staging."
        tone = "info"

    return {
        "seed_counts": seed_counts,
        "total_seeds": total_seeds,
        "ready_to_crawl": ready_to_crawl,
        "discovered": discovered,
        "crawled": crawled,
        "failed": failed,
        "skipped": skipped,
        "invalid": invalid,
        "needs_review_seed": needs_review_seed,
        "done_seeds": done_seeds,
        "pending_seeds": pending_seeds,
        "progress_pct": (
            pipeline_progress_pct if active_stage in PIPELINE_STAGES or is_complete
            else _ratio(wikipedia_enrich.get("attempted", 0), wikipedia_enrich.get("total", 0))
            if wikipedia_running
            else _ratio(web_scrape.get("processed", 0), web_scrape.get("total", 0))
            if web_scrape_running
            else _ratio(programs_crawl.get("processed", 0), programs_crawl.get("total", 0))
            if programs_crawl_running
            else gem_pct if (is_gemini and (gem_total or gem_majors.get("total")))
            else _ratio(done_seeds, total_seeds)
        ),
        "is_gemini": is_gemini,
        "gem": gem,
        "gem_total": gem_total,
        "gem_attempted": gem_attempted,
        "gem_running": gem_running,
        "gem_majors": gem_majors,
        "majors_running": majors_running,
        "wikipedia_enrich": wikipedia_enrich,
        "wikipedia_running": wikipedia_running,
        "web_scrape": web_scrape,
        "web_scrape_running": web_scrape_running,
        "programs_crawl": programs_crawl,
        "programs_crawl_running": programs_crawl_running,
        "universities": universities,
        "majors": majors,
        "pages": pages,
        "issues": issues,
        "clean_universities": clean_universities,
        "clean_majors": clean_majors,
        "clean_total": clean_universities + clean_majors,
        "not_validated": not_validated,
        "review_pending": review_pending,
        "is_active": is_active or gem_running,
        "has_staging": has_staging,
        "phase_label": phase_label,
        "phase_detail": phase_detail,
        "tone": tone,
        "execution_mode": execution_mode,
        "coverage_detail": coverage_detail,
        "coverage_pct": coverage_pct,
        "eligible_seeds": eligible_seeds,
        "staged_seeds": staged_seeds,
        "unresolved_seeds": unresolved_seeds,
        "terminal_seeds": terminal_seeds,
        "last_heartbeat": run.worker_heartbeat_at,
        "retry_count": run.retry_count,
        "next_retry_at": run.next_retry_at,
        "active_stage": active_stage,
        "stage_number": stage_number,
        "stage_count": len(PIPELINE_STAGES),
        "stage_processed": stage_processed,
        "stage_total": stage_total,
        "current_item": stage_progress.get("current_item", ""),
        "current_url": stage_progress.get("current_url", ""),
        "stage_updated_at": stage_progress.get("updated_at", ""),
        "stage_metrics": stage_progress,
        "is_untracked_legacy": is_untracked_legacy,
        "is_stale": is_stale,
    }


def _attach_run_progress(runs):
    rows = list(runs)
    for run in rows:
        run.progress = _run_progress(run)
    return rows


def _field_quality_matrix(qs=None) -> list[dict]:
    qs = qs or ExtractedUniversity.objects.all()
    total = qs.count()
    rows = []
    for field in UNIVERSITY_CSV_FIELDS:
        field_qs = qs
        if field in UNIVERSITY_BOOL_FIELDS | UNIVERSITY_INT_FIELDS:
            filled = field_qs.exclude(**{f"{field}__isnull": True}).count()
        else:
            filled = field_qs.exclude(**{field: ""}).count()
        evidence = FieldEvidence.objects.filter(entity_type="university", field_name=field)
        evidence_count = evidence.values("entity_id").distinct().count()
        avg_conf = evidence.aggregate(avg=Avg("confidence_score"))["avg"] or 0
        rows.append({
            "field": field,
            "filled": filled,
            "missing": max(total - filled, 0),
            "filled_pct": _ratio(filled, total),
            "evidence_count": evidence_count,
            "evidence_pct": _ratio(evidence_count, total),
            "avg_confidence": round(avg_conf, 2),
            "avg_confidence_pct": _ratio(avg_conf, 1),
        })
    return rows


def _evidence_counts(entity_type: str, ids) -> dict[int, int]:
    if not ids:
        return {}
    return {
        row["entity_id"]: row["n"]
        for row in FieldEvidence.objects.filter(entity_type=entity_type, entity_id__in=ids)
        .values("entity_id").annotate(n=Count("pk"))
    }


def _issue_counts(entity_type: str, ids) -> dict[int, int]:
    if not ids:
        return {}
    return {
        row["entity_id"]: row["n"]
        for row in ValidationIssue.objects.filter(entity_type=entity_type, entity_id__in=ids)
        .values("entity_id").annotate(n=Count("pk"))
    }


def _attach_counts(rows, entity_type: str):
    ids = [obj.pk for obj in rows]
    evidences = _evidence_counts(entity_type, ids)
    issues = _issue_counts(entity_type, ids)
    for obj in rows:
        obj.evidence_count = evidences.get(obj.pk, 0)
        obj.issue_count = issues.get(obj.pk, 0)
    return rows


def _quality_stage_status(run: PipelineRun | None) -> str:
    """Describe whether the automatic quality stage has reached this run yet."""
    if run is None:
        return ""
    state = run.execution_state or {}
    completed = set(state.get("completed_stages") or [])
    active_stage = state.get("current_stage") or ""
    if "ai_fields" in completed:
        return "completed"
    if active_stage == "ai_fields":
        return "running"
    if run.status in {
        PipelineRun.Status.PENDING,
        PipelineRun.Status.QUEUED,
        PipelineRun.Status.DISCOVERING,
        PipelineRun.Status.CRAWLING,
        PipelineRun.Status.RETRYING,
    }:
        return "pending"
    return ""


def _quality_status(university, field: str, run: PipelineRun | None = None) -> dict:
    metadata = (university.normalized_json or {}).get("_quality_resolution") or {}
    resolution = metadata.get(field) or {}
    status = resolution.get("status") or "not_checked"
    stage_status = _quality_stage_status(run)
    if status == "not_checked" and stage_status == "pending":
        status = "waiting_for_ai"
    elif status == "not_checked" and stage_status == "running":
        status = "checking_with_ai"
    labels = {
        "verified": "Verified",
        "verified_absent": "Not ranked (QS/THE)" if field == "global_rank" else "Verified absent",
        "unavailable": "",
        "error": "",
        "not_checked": "Not checked",
        "waiting_for_ai": "Waiting for AI",
        "checking_with_ai": "AI checking",
    }
    tones = {
        "verified": "valid",
        "verified_absent": "unknown",
        "unavailable": "unknown",
        "error": "error",
        "not_checked": "not_validated",
        "waiting_for_ai": "not_validated",
        "checking_with_ai": "warning",
    }
    reason = resolution.get("reason") or ""
    source = resolution.get("source_url") or ""
    provider = resolution.get("provider") or ""
    title_parts = [part for part in (f"provider={provider}" if provider else "", source, reason) if part]
    if not title_parts and status == "waiting_for_ai":
        title_parts.append("Automatic Fanar/Gemini checks begin at Step 4/6 after crawling")
    elif not title_parts and status == "checking_with_ai":
        title_parts.append("Fanar checks each missing field; Gemini verifies unresolved fields")
    title = " | ".join(title_parts) or labels.get(status, status)
    return {
        "status": status,
        "label": labels.get(status, status.replace("_", " ").title()),
        "tone": tones.get(status, "unknown"),
        "title": title,
        "source_url": source,
    }


def _attach_quality_statuses(universities, run: PipelineRun | None = None):
    for university in universities:
        campus_resolution = (
            ((university.normalized_json or {}).get("_quality_resolution") or {})
            .get("university_campuses") or {}
        )
        # Do not display legacy Fanar v1 counts. They were generated without an
        # official source and may include affiliated colleges or study centres.
        university.display_university_campuses = (
            None
            if campus_resolution.get("provider") == "fanar"
            and not campus_resolution.get("source_url")
            else university.university_campuses
        )
        for field in (
            "financials", "university_campuses", "admissions_contact", "admissions_phone",
            "global_rank", "campus_student_life",
        ):
            setattr(university, f"{field}_quality", _quality_status(university, field, run))
    return universities


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_int(value, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(parsed, maximum)


def _empty_filter(qs, field: str):
    if field in UNIVERSITY_BOOL_FIELDS | UNIVERSITY_INT_FIELDS:
        return qs.filter(**{f"{field}__isnull": True})
    return qs.filter(Q(**{field: ""}) | Q(**{f"{field}__isnull": True}))


def _clean_university_qs(qs):
    qs = qs.filter(review_status__in=CLEAN_REVIEW_STATUSES,
                   validation_status__in=CLEAN_VALIDATION_STATUSES)
    for field in _required_university_export_fields():
        if field in UNIVERSITY_INT_FIELDS:
            qs = qs.exclude(**{f"{field}__isnull": True})
        elif field in UNIVERSITY_BOOL_FIELDS:
            qs = qs.exclude(**{f"{field}__isnull": True})
        else:
            qs = qs.exclude(Q(**{field: ""}) | Q(**{f"{field}__isnull": True}))
    return qs


def _clean_major_qs(qs):
    return qs.filter(review_status__in=CLEAN_REVIEW_STATUSES,
                     validation_status__in=CLEAN_VALIDATION_STATUSES).filter(
        Q(is_higher_education_program=True) | Q(review_status__in=CLEAN_REVIEW_STATUSES)
    )


def _apply_university_filters(qs, request):
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(location__icontains=q) | Q(slug__icontains=q)
            | Q(website__icontains=q) | Q(country__icontains=q)
        )
    validation = request.GET.get("validation") or request.GET.get("status")
    if validation:
        qs = qs.filter(validation_status=validation)
    review = request.GET.get("review")
    if review:
        qs = qs.filter(review_status=review)
    institution_type = request.GET.get("institution_type")
    if institution_type:
        qs = qs.filter(institution_type=institution_type)
    has_website = request.GET.get("has_website")
    if has_website == "yes":
        qs = qs.exclude(website="")
    elif has_website == "no":
        qs = qs.filter(website="")
    missing_field = request.GET.get("missing_field", "").strip()
    if missing_field in UNIVERSITY_REVIEW_FIELDS:
        qs = _empty_filter(qs, missing_field)
    min_confidence = _parse_float(request.GET.get("min_confidence"))
    if min_confidence is not None:
        qs = qs.filter(confidence_score__gte=min_confidence)
    sort = request.GET.get("sort", "confidence")
    qs = qs.order_by(*UNIVERSITY_SORTS.get(sort, UNIVERSITY_SORTS["confidence"]))
    return qs, {
        "q": q, "validation": validation or "", "review": review or "",
        "institution_type": institution_type or "", "has_website": has_website or "",
        "missing_field": missing_field, "min_confidence": request.GET.get("min_confidence", ""),
        "sort": sort,
    }


def _apply_major_filters(qs, request):
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(program_name__icontains=q) | Q(program_url__icontains=q)
            | Q(source_url__icontains=q) | Q(field_of_study__icontains=q)
            | Q(extracted_university__name__icontains=q)
        )
    university = request.GET.get("university", "").strip()
    if university:
        if university.isdigit():
            qs = qs.filter(extracted_university_id=int(university))
        else:
            qs = qs.filter(extracted_university__name__icontains=university)
    degree_level = request.GET.get("degree_level", "")
    if degree_level:
        qs = qs.filter(degree_level=degree_level)
    validation = request.GET.get("validation") or request.GET.get("status")
    if validation:
        qs = qs.filter(validation_status=validation)
    review = request.GET.get("review")
    if review:
        qs = qs.filter(review_status=review)
    higher_ed = request.GET.get("higher_ed") or request.GET.get("he")
    if higher_ed in ("yes", "true"):
        qs = qs.filter(is_higher_education_program=True)
    elif higher_ed in ("no", "false"):
        qs = qs.filter(is_higher_education_program=False)
    elif higher_ed == "uncertain":
        qs = qs.filter(is_higher_education_program__isnull=True)
    has_url = request.GET.get("has_url")
    if has_url == "yes":
        qs = qs.exclude(program_url="")
    elif has_url == "no":
        qs = qs.filter(program_url="")
    min_confidence = _parse_float(request.GET.get("min_confidence"))
    if min_confidence is not None:
        qs = qs.filter(confidence_score__gte=min_confidence)
    sort = request.GET.get("sort", "university")
    qs = qs.order_by(*MAJOR_SORTS.get(sort, MAJOR_SORTS["university"]))
    return qs, {
        "q": q, "university": university, "degree_level": degree_level,
        "validation": validation or "", "review": review or "",
        "higher_ed": higher_ed or "", "has_url": has_url or "",
        "min_confidence": request.GET.get("min_confidence", ""), "sort": sort,
    }


def _bool_from_post(value):
    normalized = normalize_bool(value)
    return normalized


def _university_value_from_post(field: str, request):
    if field in UNIVERSITY_BOOL_FIELDS:
        return _bool_from_post(request.POST.get(field, ""))
    if field in UNIVERSITY_INT_FIELDS:
        return normalize_int(request.POST.get(field, ""))
    if field in UNIVERSITY_URL_FIELDS:
        return normalize_url(request.POST.get(field, ""))
    if field == "admissions_phone":
        return normalize_phone(request.POST.get(field, ""))
    if field == "admissions_contact":
        return normalize_email(request.POST.get(field, ""))
    return (request.POST.get(field, "") or "").strip()


def _major_value_from_post(field: str, request):
    if field in {"program_url", "source_url"}:
        return normalize_url(request.POST.get(field, ""))
    return (request.POST.get(field, "") or "").strip()


def _manual_evidence(entity_type: str, entity_id: int, field: str, value, note: str = ""):
    if value in ("", None):
        return
    FieldEvidence.objects.create(
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field,
        extracted_value=str(value)[:5000],
        normalized_value=str(value)[:5000],
        text_snippet=(note or f"Manual review value for {field}: {value}")[:500],
        confidence_score=1.0,
        extractor_name="human_review",
        extraction_method="manual",
        crawled_at=timezone.now(),
    )


def dashboard(request):
    _recover_stale_pipeline_runs()
    runs = _attach_run_progress(PipelineRun.objects.order_by("-created_at")[:10])
    universities = ExtractedUniversity.objects.all()
    majors = ExtractedProgram.objects.select_related("extracted_university")
    latest_run = PipelineRun.objects.order_by("-created_at").first()
    latest_run_progress = _run_progress(latest_run) if latest_run else None
    context = {
        "runs": runs,
        "total_runs": PipelineRun.objects.count(),
        "total_seeds": InstitutionSeed.objects.count(),
        "total_universities": universities.count(),
        "total_programs": majors.count(),
        "total_imported": University.objects.count(),
        "total_imported_programs": Program.objects.count(),
        "total_evidence": FieldEvidence.objects.count(),
        "total_issues": ValidationIssue.objects.count(),
        "pending_reviews": ExtractedUniversity.objects.filter(review_status=ReviewStatus.PENDING).count(),
        "approved_reviews": ExtractedUniversity.objects.filter(review_status=ReviewStatus.APPROVED).count(),
        "rejected_reviews": ExtractedUniversity.objects.filter(review_status=ReviewStatus.REJECTED).count(),
        "valid_universities": ExtractedUniversity.objects.filter(validation_status="valid").count(),
        "warning_universities": ExtractedUniversity.objects.filter(validation_status="warnings").count(),
        "invalid_universities": ExtractedUniversity.objects.filter(validation_status="invalid").count(),
        "total_clean_universities": _clean_university_qs(universities).count(),
        "total_clean_majors": _clean_major_qs(majors).count(),
        "latest_run": latest_run,
        "latest_run_progress": latest_run_progress,
        "auto_refresh": bool(
            (latest_run_progress and latest_run_progress["is_active"])
            or DataResetJob.active().exists()
        ),
        "funnel": _dashboard_funnel(),
        "university_validation_chart": _distribution(universities, "validation_status", ValidationStatus.choices),
        "university_review_chart": _distribution(universities, "review_status", ReviewStatus.choices),
        "major_validation_chart": _distribution(majors, "validation_status", ValidationStatus.choices),
        "major_degree_chart": _distribution(majors, "degree_level", DegreeLevel.choices),
        "major_higher_ed_chart": [
            {"label": "yes", "count": majors.filter(is_higher_education_program=True).count(),
             "pct": _ratio(majors.filter(is_higher_education_program=True).count(), majors.count())},
            {"label": "no", "count": majors.filter(is_higher_education_program=False).count(),
             "pct": _ratio(majors.filter(is_higher_education_program=False).count(), majors.count())},
            {"label": "uncertain", "count": majors.filter(is_higher_education_program__isnull=True).count(),
             "pct": _ratio(majors.filter(is_higher_education_program__isnull=True).count(), majors.count())},
        ],
        "field_quality": _field_quality_matrix(universities),
        "country_options": _get_country_options(),
        "default_max_pages": settings.ETL_MAX_PAGES_PER_SITE,
        "gemini_configured": gemini_is_configured(),
        "fanar_configured": _fanar_configured(),
        "llm_providers": _llm_provider_status(),
        "schedules": CrawlSchedule.objects.filter(is_active=True).order_by("country_name")[:10],
        "latest_reset_job": DataResetJob.objects.order_by("-requested_at").first(),
        "reset_active": DataResetJob.active().exists(),
    }
    # Chart.js JSON data (must be after context dict is built)
    context["funnel_json"] = json.dumps(context["funnel"])
    context["validation_json"] = json.dumps(context["university_validation_chart"])
    context["review_json"] = json.dumps(context["university_review_chart"])
    context["degree_json"] = json.dumps(context["major_degree_chart"])
    context["country_json"] = json.dumps(list(
        universities.exclude(country="").values("country")
        .annotate(n=Count("pk")).order_by("-n")[:15]
    ))
    return render(request, "academic_etl/dashboard.html", context)


def _fanar_configured():
    try:
        from .services.fanar_enrich import fanar_is_configured
        return fanar_is_configured()
    except Exception:
        return False


def _llm_provider_status():
    try:
        from .services.llm_provider import get_provider_status
        return get_provider_status()
    except Exception:
        return []


@require_POST
def start_country_run(request):
    selected_country = request.POST.get("country", "").strip()
    custom_country = request.POST.get("custom_country", "").strip()
    country = custom_country if selected_country == "__custom__" else selected_country
    country_code = request.POST.get("country_code", "").strip()
    name, code = resolve_country(country, country_code)
    if not name:
        messages.error(request, "Choose a country or enter a custom country name.")
        return redirect("academic_etl:dashboard")

    mode = request.POST.get("mode", "crawl")
    discover_limit = _positive_int(request.POST.get("discover_limit"), 50, 500)
    crawl_limit = _positive_int(request.POST.get("crawl_limit"), 5, 100)
    max_pages = _positive_int(request.POST.get("max_pages"), 6, 30)
    run = PipelineRun.objects.create(
        country_name=name,
        country_code=code,
        crawl_mode="full" if mode == "crawl" else "discover_only",
        seed_provider="hipolabs",
    )
    try:
        run_discovery(run, limit=discover_limit)
        if mode == "crawl":
            crawl_run(run, limit=crawl_limit, crawler=SiteCrawler(max_pages=max_pages))
            messages.success(
                request,
                f"Run #{run.pk} created for {name}: discovered {run.seeds.count()} seeds and crawled up to {crawl_limit}.",
            )
        else:
            messages.success(request, f"Run #{run.pk} created for {name}: discovered {run.seeds.count()} seeds.")
    except Exception as exc:
        run.status = PipelineRun.Status.FAILED
        run.error_message = str(exc)[:2000]
        run.save(update_fields=["status", "error_message", "updated_at"])
        messages.error(request, f"Run #{run.pk} failed: {exc}")
    return redirect("academic_etl:run_detail", run_id=run.pk)


def _gemini_runner(run_id: int, strategy: str = "hybrid", use_cache: bool = True,
                   crawl_limit: int = 40, max_pages: int = 8):
    """Background thread: enrich a run then validate it. Progress is written to the
    run's stats_json as it goes, so the page can show it live.

    strategy="hybrid": Wikipedia + official-site crawl fill first, then Gemini only
    fills remaining gaps. strategy="gemini_primary" is kept for explicit debugging
    only and may overwrite staged fields."""
    from django.db import connection
    try:
        run = PipelineRun.objects.get(pk=run_id)
        try:
            if strategy == "majors":
                enrich_run_majors_from_gemini(run, use_cache=use_cache)
            elif strategy == "hybrid":
                from .services.crawler import SiteCrawler
                enrich_run_from_wikipedia(run)
                crawl_run(run, limit=crawl_limit, crawler=SiteCrawler(max_pages=max_pages))
                enrich_run_from_gemini(run, use_cache=use_cache, overwrite=False,
                                       skip_complete=True)
            elif strategy == "gemini_primary":
                enrich_run_from_gemini(run, use_cache=use_cache, overwrite=True)
            else:
                enrich_run_from_gemini(run, use_cache=use_cache, overwrite=False,
                                       skip_complete=True)
            validate_run(run)
        except Exception as exc:  # noqa: BLE001 - surfaced via run.error_message
            run.status = PipelineRun.Status.FAILED
            run.error_message = str(exc)[:2000]
            run.save(update_fields=["status", "error_message", "updated_at"])
    finally:
        connection.close()  # each thread owns its DB connection


def _launch_gemini(run_id: int, strategy: str = "hybrid", use_cache: bool = True,
                   crawl_limit: int = 40, max_pages: int = 8):
    threading.Thread(
        target=_gemini_runner,
        args=(run_id, strategy, use_cache, crawl_limit, max_pages), daemon=True,
    ).start()


@require_POST
def start_gemini_run(request):
    """Create a run, discover the Wikipedia roster (fast, synchronous), then kick
    off Gemini grounded enrichment in a background thread. Redirects to the run
    page, which auto-refreshes to show live progress."""
    if not gemini_is_configured():
        messages.error(request, "No Gemini API key configured. Add GEMINI_API_KEY "
                                "(or GEMINI_API_KEYS) to the .env file, then retry.")
        return redirect("academic_etl:dashboard")

    selected_country = request.POST.get("country", "").strip()
    custom_country = request.POST.get("custom_country", "").strip()
    country = custom_country if selected_country == "__custom__" else selected_country
    country_code = request.POST.get("country_code", "").strip()
    name, code = resolve_country(country, country_code)
    if not name:
        messages.error(request, "Choose a country or enter a custom country name.")
        return redirect("academic_etl:dashboard")

    discover_limit = _positive_int(request.POST.get("discover_limit"), 0, 1000)
    use_cache = request.POST.get("no_cache") != "1"
    strategy = "gemini_primary" if request.POST.get("strategy") == "gemini_primary" else "hybrid"
    crawl_limit = _positive_int(request.POST.get("crawl_limit"), 40, 200)
    max_pages = _positive_int(request.POST.get("max_pages"), 8, 30)
    run = PipelineRun.objects.create(
        country_name=name, country_code=code,
        crawl_mode="full", seed_provider="wikipedia", crawl_scope="gemini_grounding",
    )
    try:
        run_discovery(run, limit=discover_limit)
    except Exception as exc:
        run.status = PipelineRun.Status.FAILED
        run.error_message = str(exc)[:2000]
        run.save(update_fields=["status", "error_message", "updated_at"])
        messages.error(request, f"Run #{run.pk} discovery failed: {exc}")
        return redirect("academic_etl:run_detail", run_id=run.pk)

    valid = run.seeds.filter(status=InstitutionSeed.Status.VALID).count()
    _launch_gemini(run.pk, strategy=strategy, use_cache=use_cache,
                   crawl_limit=crawl_limit, max_pages=max_pages)
    label = (
        "Crawl-first (Wikipedia + official crawl + Gemini gap-fill)"
        if strategy == "hybrid" else "Gemini primary"
    )
    messages.success(
        request,
        f"Run #{run.pk} for {name}: discovered {run.seeds.count()} seeds ({valid} valid). "
        f"{label} is running in the background — this page refreshes with progress.",
    )
    return redirect("academic_etl:run_detail", run_id=run.pk)


@require_POST
def run_gemini_action(request, run_id):
    """(Re)run crawl-first AI gap-fill on an existing run in the background.
    Useful to fill the remaining gaps after a quota reset or after adding more API keys."""
    run = get_object_or_404(PipelineRun, pk=run_id)
    if not gemini_is_configured():
        messages.error(request, "No Gemini API key configured. Add GEMINI_API_KEY "
                                "(or GEMINI_API_KEYS) to the .env file, then retry.")
        return redirect("academic_etl:run_detail", run_id=run.pk)
    gem = (run.stats_json or {}).get("gemini_enrich") or {}
    if run.status == PipelineRun.Status.CRAWLING and not gem.get("done"):
        messages.info(request, "AI gap-fill is already running for this run.")
        return redirect("academic_etl:run_detail", run_id=run.pk)
    use_cache = request.POST.get("no_cache") != "1"
    _launch_gemini(run.pk, use_cache=use_cache)
    messages.success(request, f"AI gap-fill started for run #{run.pk} "
                              f"(background). This page refreshes with progress.")
    return redirect("academic_etl:run_detail", run_id=run.pk)


@require_POST
def run_majors_action(request, run_id):
    """Fetch each staged university's majors via Gemini (grounded) in the
    background, storing them as ExtractedProgram rows (1-to-many)."""
    run = get_object_or_404(PipelineRun, pk=run_id)
    if not gemini_is_configured():
        messages.error(request, "No Gemini API key configured. Add GEMINI_API_KEY "
                                "(or GEMINI_API_KEYS) to the .env file, then retry.")
        return redirect("academic_etl:run_detail", run_id=run.pk)
    if not run.universities.exists():
        messages.error(request, "No staged universities yet — run university enrichment first.")
        return redirect("academic_etl:run_detail", run_id=run.pk)
    gm = (run.stats_json or {}).get("gemini_majors") or {}
    if run.status == PipelineRun.Status.CRAWLING and not gm.get("done"):
        messages.info(request, "A Gemini job is already running for this run.")
        return redirect("academic_etl:run_detail", run_id=run.pk)
    use_cache = request.POST.get("no_cache") != "1"
    _launch_gemini(run.pk, strategy="majors", use_cache=use_cache)
    messages.success(request, f"Majors enrichment started for run #{run.pk} "
                              f"(background). This page refreshes with progress.")
    return redirect("academic_etl:run_detail", run_id=run.pk)


@require_POST
def run_delete_action(request, run_id):
    """Delete a pipeline run and all its staged data (seeds, pages, universities,
    programs, evidence, issues, import jobs cascade via FK)."""
    run = get_object_or_404(PipelineRun, pk=run_id)
    label = f"#{run.pk} {run.country_name}"
    run.delete()
    messages.success(request, f"Deleted run {label} and all its staged data.")
    return redirect("academic_etl:runs_list")


@require_POST
def run_crawl_action(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    crawl_limit = _positive_int(request.POST.get("crawl_limit"), 5, 100)
    max_pages = _positive_int(request.POST.get("max_pages"), 6, 30)
    try:
        stats = crawl_run(run, limit=crawl_limit, crawler=SiteCrawler(max_pages=max_pages))
        messages.success(request, f"Crawl finished for run #{run.pk}: {stats}.")
    except Exception as exc:
        messages.error(request, f"Crawl failed for run #{run.pk}: {exc}")
    return redirect("academic_etl:run_detail", run_id=run.pk)


@require_POST
def run_validate_action(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    try:
        stats = validate_run(run)
        messages.success(request, f"Validation finished for run #{run.pk}: {stats}.")
    except Exception as exc:
        messages.error(request, f"Validation failed for run #{run.pk}: {exc}")
    return redirect("academic_etl:run_detail", run_id=run.pk)


@require_POST
def run_normalize_data_action(request, run_id):
    """Repair existing staged contact and URL values without re-crawling."""
    run = get_object_or_404(PipelineRun, pk=run_id)
    try:
        stats = _post_process_run(run)
        validate_run(run)
        messages.success(
            request,
            f"Normalized run #{run.pk}: {stats['fixed']} records fixed, {stats['removed']} junk rows removed.",
        )
    except Exception as exc:
        messages.error(request, f"Could not normalize run #{run.pk}: {exc}")
    return redirect("academic_etl:universities_list", run_id=run.pk)


@require_POST
def run_approve_all_action(request, run_id):
    """Bulk-approve every valid/warnings record so the Clean pages and CSV export
    populate without per-record clicking. needs_review rows (conflicts, non-
    English) are deliberately left for manual review."""
    run = get_object_or_404(PipelineRun, pk=run_id)
    unis = run.universities.filter(validation_status__in=CLEAN_VALIDATION_STATUSES) \
        .exclude(review_status=ReviewStatus.REJECTED).update(review_status=ReviewStatus.APPROVED)
    progs = run.programs.filter(validation_status__in=CLEAN_VALIDATION_STATUSES) \
        .exclude(review_status=ReviewStatus.REJECTED) \
        .exclude(is_higher_education_program=False).update(review_status=ReviewStatus.APPROVED)
    messages.success(request, f"Approved {unis} universities and {progs} majors "
                              f"(valid/warnings). needs_review rows left for manual review.")
    return redirect("academic_etl:run_detail", run_id=run.pk)


@require_POST
def run_import_action(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    dry_run = request.POST.get("dry_run", "1") == "1"
    approved_only = request.POST.get("approved_only", "1") == "1"
    threshold = _parse_float(request.POST.get("confidence_threshold")) or settings.ETL_IMPORT_CONFIDENCE_THRESHOLD
    job = import_run(run, dry_run=dry_run, approved_only=approved_only, threshold=threshold)
    if job.status == ImportJob.Status.COMPLETED:
        messages.success(request, f"Import job #{job.pk} completed.")
    else:
        messages.error(request, f"Import job #{job.pk} failed: {job.error_message}")
    return redirect("academic_etl:import_job_detail", pk=job.pk)


def runs_list(request):
    _recover_stale_pipeline_runs()
    runs = PipelineRun.objects.annotate(
        n_seeds=Count("seeds", distinct=True),
        n_unis=Count("universities", distinct=True),
    ).order_by("-created_at")
    runs = _attach_run_progress(runs)
    return render(request, "academic_etl/runs_list.html", {
        "runs": runs,
        "auto_refresh": any(run.progress["is_active"] for run in runs),
    })


def run_detail(request, run_id):
    _recover_stale_pipeline_runs()
    run = get_object_or_404(PipelineRun, pk=run_id)
    progress = _run_progress(run)
    seed_stats = run.seeds.values("status").annotate(n=Count("pk")).order_by("status")
    uni_stats = run.universities.values("validation_status").annotate(n=Count("pk"))
    program_stats = run.programs.values("validation_status").annotate(n=Count("pk"))
    review_stats = run.universities.values("review_status").annotate(n=Count("pk"))
    return render(request, "academic_etl/run_detail.html", {
        "run": run, "seed_stats": seed_stats, "uni_stats": uni_stats,
        "program_stats": program_stats, "review_stats": review_stats,
        "progress": progress, "auto_refresh": progress["is_active"],
        "import_jobs": run.import_jobs.order_by("-created_at"),
        "recent_issues": run.issues.order_by("-created_at")[:20],
    })


def run_progress_json(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    progress = _run_progress(run)
    return JsonResponse({
        "run_id": run.pk,
        "status": run.status,
        "current_step": (run.stats_json or {}).get("current_step", ""),
        "phase_label": progress["phase_label"],
        "phase_detail": progress["phase_detail"],
        "progress_pct": progress["progress_pct"],
        "coverage_detail": progress["coverage_detail"],
        "stage": progress["active_stage"],
        "stage_number": progress["stage_number"],
        "stage_count": progress["stage_count"],
        "processed": progress["stage_processed"],
        "total": progress["stage_total"],
        "current_item": progress["current_item"],
        "current_url": progress["current_url"],
        "fanar_calls": progress["stage_metrics"].get("fanar_calls", 0),
        "gemini_calls": progress["stage_metrics"].get("gemini_calls", 0),
        "verified_fields": progress["stage_metrics"].get("verified_fields", 0),
        "field_errors": progress["stage_metrics"].get("errors", 0),
        "universities": progress["universities"],
        "majors": progress["majors"],
        "heartbeat_at": run.worker_heartbeat_at.isoformat() if run.worker_heartbeat_at else None,
        "stage_updated_at": progress["stage_updated_at"] or None,
        "retry_count": run.retry_count,
        "next_retry_at": run.next_retry_at.isoformat() if run.next_retry_at else None,
        "is_stale": progress["is_stale"],
        "is_untracked_legacy": progress["is_untracked_legacy"],
        "terminal": run.status in {
            PipelineRun.Status.REVIEW,
            PipelineRun.Status.COMPLETED,
            PipelineRun.Status.FAILED,
            PipelineRun.Status.CANCELLED,
        },
    })


def seeds_list(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    seeds = run.seeds.order_by("status", "name")
    status = request.GET.get("status")
    if status:
        seeds = seeds.filter(status=status)
    return render(request, "academic_etl/seeds_list.html",
                  {"run": run, "seeds": seeds, "status_filter": status or ""})


def universities_list(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    unis, filters = _apply_university_filters(run.universities.all(), request)
    rows = _attach_quality_statuses(_attach_counts(list(unis), "university"), run)
    return render(request, "academic_etl/universities_list.html",
                  {"run": run, "universities": rows, "filters": filters,
                   "status_filter": filters["validation"], "review_filter": filters["review"],
                   "university_fields": UNIVERSITY_CSV_FIELDS,
                   "validation_choices": ValidationStatus.choices,
                   "review_choices": ReviewStatus.choices,
                   "institution_type_choices": ExtractedUniversity._meta.get_field("institution_type").choices,
                   "sort_choices": UNIVERSITY_SORTS.keys(),
                   "quality_stage_status": _quality_stage_status(run)})


def university_detail(request, pk):
    uni = get_object_or_404(ExtractedUniversity, pk=pk)
    evidence = FieldEvidence.objects.filter(entity_type="university", entity_id=uni.pk)
    evidence_by_field = {}
    for ev in evidence.order_by("-confidence_score"):
        evidence_by_field.setdefault(ev.field_name, []).append(ev)

    existing, matched_by = _match_university(uni)
    source_conflicts = set((uni.normalized_json or {}).get("source_conflicts") or [])
    rows = []
    for field in UNIVERSITY_REVIEW_FIELDS:
        if field in UNIVERSITY_BOOL_FIELDS:
            input_type = "bool"
        elif field in ("description", "campus_student_life"):
            input_type = "textarea"
        else:
            input_type = "text"
        field_evidence = evidence_by_field.get(field, [])
        rows.append({
            "field": field,
            "value": getattr(uni, field),
            "db_value": getattr(existing, field, "") if existing else "",
            "evidence": field_evidence,
            # KB-asserted (Wikidata/Wikipedia) values shown alongside the official site.
            "source_evidence": [e for e in field_evidence if e.extraction_method == "wikidata"],
            "source_conflict": field in source_conflicts,
            "quality": _quality_status(uni, field, uni.pipeline_run),
            "input_type": input_type,
        })
    issues = ValidationIssue.objects.filter(entity_type="university", entity_id=uni.pk)
    return render(request, "academic_etl/university_detail.html", {
        "uni": uni, "rows": rows, "issues": issues,
        "existing": existing, "matched_by": matched_by,
        "programs": uni.programs.order_by("-confidence_score"),
        "pages": uni.seed.pages.order_by("depth") if uni.seed else [],
        "degree_level_choices": DegreeLevel.choices,
    })


@require_POST
def university_action(request, pk):
    uni = get_object_or_404(ExtractedUniversity, pk=pk)
    action = request.POST.get("action")
    if action == "approve":
        uni.review_status = ReviewStatus.APPROVED
        messages.success(request, f"Approved {uni.name}.")
    elif action in ("reject", "delete"):
        uni.review_status = ReviewStatus.REJECTED
        messages.warning(request, f"Rejected {uni.name}.")
    elif action == "edit":
        changed = []
        for field in UNIVERSITY_REVIEW_FIELDS:
            if field in request.POST:
                new = _university_value_from_post(field, request)
                old = getattr(uni, field)
                if str(old if old is not None else "") != str(new if new is not None else ""):
                    setattr(uni, field, new)
                    changed.append(field)
        if changed:
            if not uni.slug and uni.name:
                uni.slug = make_slug(uni.name, uni.city)
            uni.review_status = ReviewStatus.EDITED
            for field in changed:
                _manual_evidence("university", uni.pk, field, getattr(uni, field), "Edited during human review.")
            messages.success(request, f"Saved edits to: {', '.join(changed)}.")
        else:
            messages.info(request, "No changes.")
    uni.review_notes = request.POST.get("notes", uni.review_notes)
    uni.save()
    return redirect("academic_etl:university_detail", pk=uni.pk)


def programs_list(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    programs, filters = _apply_major_filters(run.programs.select_related("extracted_university"), request)
    rows = _attach_counts(list(programs), "program")
    return render(request, "academic_etl/programs_list.html",
                  {"run": run, "programs": rows, "filters": filters,
                   "status_filter": filters["validation"], "he_filter": filters["higher_ed"],
                   "degree_level_choices": DegreeLevel.choices,
                   "validation_choices": ValidationStatus.choices,
                   "review_choices": ReviewStatus.choices,
                   "sort_choices": MAJOR_SORTS.keys()})


def program_detail(request, pk):
    program = get_object_or_404(ExtractedProgram, pk=pk)
    evidence = FieldEvidence.objects.filter(entity_type="program", entity_id=program.pk)
    evidence_by_field = {}
    for ev in evidence.order_by("-confidence_score"):
        evidence_by_field.setdefault(ev.field_name, []).append(ev)
    issues = ValidationIssue.objects.filter(entity_type="program", entity_id=program.pk)
    rows = []
    for field in PROGRAM_REVIEW_FIELDS:
        if field in ("description", "admission_requirements", "career_outcomes"):
            input_type = "textarea"
        elif field == "degree_level":
            input_type = "degree"
        else:
            input_type = "text"
        rows.append({"field": field, "value": getattr(program, field),
                     "input_type": input_type, "evidence": evidence_by_field.get(field, [])})
    return render(request, "academic_etl/program_detail.html",
                  {"program": program, "evidence": evidence, "issues": issues,
                   "rows": rows, "degree_level_choices": DegreeLevel.choices})


@require_POST
def program_action(request, pk):
    program = get_object_or_404(ExtractedProgram, pk=pk)
    action = request.POST.get("action")
    if action == "approve":
        program.review_status = ReviewStatus.APPROVED
        if program.is_higher_education_program is None:
            program.is_higher_education_program = True  # reviewer confirmed
        messages.success(request, f"Approved {program.program_name}.")
    elif action in ("reject", "delete"):
        program.review_status = ReviewStatus.REJECTED
        messages.warning(request, f"Rejected {program.program_name}.")
    elif action == "edit":
        changed = []
        for field in PROGRAM_REVIEW_FIELDS:
            if field in request.POST:
                new = _major_value_from_post(field, request)
                if str(getattr(program, field) or "") != new:
                    setattr(program, field, new)
                    changed.append(field)
        if changed:
            program.review_status = ReviewStatus.EDITED
            for field in changed:
                _manual_evidence("program", program.pk, field, getattr(program, field), "Edited during human review.")
            messages.success(request, f"Saved edits to: {', '.join(changed)}.")
    program.save()
    next_url = request.POST.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("academic_etl:program_detail", pk=program.pk)


def majors_list(request, run_id):
    """UI alias: backend still stores majors as ExtractedProgram rows."""
    return programs_list(request, run_id)


def clean_universities(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    qs = _clean_university_qs(run.universities.all())
    qs, filters = _apply_university_filters(qs, request)
    rows = _attach_counts(list(qs), "university")
    return render(request, "academic_etl/clean_universities.html", {
        "run": run,
        "universities": rows,
        "filters": filters,
        "university_fields": UNIVERSITY_CSV_FIELDS,
        "validation_choices": ValidationStatus.choices,
        "review_choices": ReviewStatus.choices,
        "institution_type_choices": ExtractedUniversity._meta.get_field("institution_type").choices,
        "sort_choices": UNIVERSITY_SORTS.keys(),
    })


def clean_majors(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    qs = _clean_major_qs(run.programs.select_related("extracted_university"))
    qs, filters = _apply_major_filters(qs, request)
    rows = _attach_counts(list(qs), "program")
    return render(request, "academic_etl/clean_majors.html", {
        "run": run,
        "programs": rows,
        "filters": filters,
        "degree_level_choices": DegreeLevel.choices,
        "validation_choices": ValidationStatus.choices,
        "review_choices": ReviewStatus.choices,
        "sort_choices": MAJOR_SORTS.keys(),
    })


def _csv_response(filename: str, header, rows) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # UTF-8 BOM so Excel reads Vietnamese/diacritics correctly
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


def export_universities_csv(request, run_id):
    """Download universities as CSV (sample-CSV shape). Default: clean/approved
    rows; pass ?all=1 for every staged university in the run."""
    from .services.financial import is_canonical_financials

    run = get_object_or_404(PipelineRun, pk=run_id)
    export_all = request.GET.get("all") == "1"
    qs = run.universities.all().order_by("name")
    if not export_all:
        qs = _clean_university_qs(qs)
        qs = [uni for uni in qs if is_canonical_financials(uni.financials, uni.country_code)]
    header, rows = university_rows(qs, english_only=not export_all)
    slug = (run.country_code or run.country_name or "run").lower().replace(" ", "_")
    return _csv_response(f"universities_{slug}_run{run.pk}.csv", header, rows)


def export_majors_csv(request, run_id):
    """Download majors/programs as CSV. Default: clean/approved rows; ?all=1 for
    every staged program in the run."""
    run = get_object_or_404(PipelineRun, pk=run_id)
    export_all = request.GET.get("all") == "1"
    qs = run.programs.select_related("extracted_university").order_by(
        "extracted_university__name", "program_name")
    if not export_all:
        qs = _clean_major_qs(qs)
    header, rows = major_rows(qs, english_only=not export_all)
    slug = (run.country_code or run.country_name or "run").lower().replace(" ", "_")
    return _csv_response(f"majors_{slug}_run{run.pk}.csv", header, rows)


def export_simple_majors_csv(request, run_id):
    """Download the minimal majors CSV (University Name | Major Name | Source URL).
    Default: clean/approved rows; ?all=1 for every staged program in the run."""
    run = get_object_or_404(PipelineRun, pk=run_id)
    export_all = request.GET.get("all") == "1"
    qs = run.programs.select_related("extracted_university").order_by(
        "extracted_university__name", "program_name")
    if not export_all:
        qs = _clean_major_qs(qs)
    header, rows = simple_major_rows(qs, english_only=not export_all)
    slug = (run.country_code or run.country_name or "run").lower().replace(" ", "_")
    return _csv_response(f"majors_simple_{slug}_run{run.pk}.csv", header, rows)


def add_university(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    if request.method == "POST":
        values = {field: _university_value_from_post(field, request) for field in UNIVERSITY_REVIEW_FIELDS}
        if not values.get("name"):
            messages.error(request, "University name is required.")
        else:
            if not values.get("slug"):
                values["slug"] = make_slug(values["name"])
            values.setdefault("country", run.country_name)
            values.setdefault("country_code", run.country_code)
            institution_type = request.POST.get("institution_type") or "university"
            uni = ExtractedUniversity.objects.create(
                pipeline_run=run,
                name=values.get("name", "")[:500],
                location=values.get("location", "")[:500],
                description=values.get("description", ""),
                slug=values.get("slug", "")[:500],
                sponsored=values.get("sponsored"),
                website=values.get("website", "")[:500],
                global_rank=values.get("global_rank", "")[:100],
                financials=values.get("financials", "")[:500],
                student_loan_available=values.get("student_loan_available"),
                campus_student_life=values.get("campus_student_life", ""),
                number_of_students=values.get("number_of_students"),
                student_to_faculty_ratio=values.get("student_to_faculty_ratio", "")[:50],
                international_student_ratio=values.get("international_student_ratio", "")[:50],
                housing_availability=values.get("housing_availability"),
                admissions_contact=values.get("admissions_contact", "")[:254],
                admissions_phone=values.get("admissions_phone", "")[:50],
                contact_person=values.get("contact_person", "")[:255],
                admissions_page_link=values.get("admissions_page_link", "")[:500],
                immigration_support=values.get("immigration_support"),
                university_campuses=values.get("university_campuses"),
                country=values.get("country") or run.country_name,
                country_code=(values.get("country_code") or run.country_code)[:2],
                institution_type=institution_type,
                confidence_score=0.9,
                validation_status=ValidationStatus.NOT_VALIDATED,
                review_status=ReviewStatus.PENDING,
                review_notes=request.POST.get("notes", "").strip(),
                raw_json={"manual": True},
                normalized_json={"manual_entry": True},
            )
            for field in UNIVERSITY_REVIEW_FIELDS:
                _manual_evidence("university", uni.pk, field, getattr(uni, field), "Manual university staging entry.")
            messages.success(request, f"Added staged university {uni.name}.")
            return redirect("academic_etl:university_detail", pk=uni.pk)
    return render(request, "academic_etl/university_form.html", {
        "run": run,
        "fields": UNIVERSITY_REVIEW_FIELDS,
        "bool_fields": UNIVERSITY_BOOL_FIELDS,
        "int_fields": UNIVERSITY_INT_FIELDS,
        "institution_type_choices": ExtractedUniversity._meta.get_field("institution_type").choices,
    })


def add_major(request, pk):
    uni = get_object_or_404(ExtractedUniversity, pk=pk)
    if request.method == "POST":
        values = {field: _major_value_from_post(field, request) for field in MAJOR_REVIEW_FIELDS}
        if not values.get("program_name"):
            messages.error(request, "Major name is required.")
        else:
            higher_ed = request.POST.get("is_higher_education_program", "")
            if higher_ed == "yes":
                is_he = True
            elif higher_ed == "no":
                is_he = False
            else:
                is_he = None
            major = ExtractedProgram.objects.create(
                pipeline_run=uni.pipeline_run,
                extracted_university=uni,
                university_slug=uni.slug,
                country=uni.country,
                country_code=uni.country_code,
                campus=values.get("campus", "")[:255],
                program_name=values.get("program_name", "")[:500],
                degree_level=values.get("degree_level") or DegreeLevel.UNKNOWN,
                field_of_study=values.get("field_of_study", "")[:255],
                faculty_or_school=values.get("faculty_or_school", "")[:255],
                description=values.get("description", ""),
                duration=values.get("duration", "")[:100],
                study_mode=values.get("study_mode", "")[:100],
                language=values.get("language", "")[:100],
                tuition_fee=values.get("tuition_fee", "")[:255],
                currency=values.get("currency", "")[:10],
                intake=values.get("intake", "")[:255],
                application_deadline=values.get("application_deadline", "")[:255],
                admission_requirements=values.get("admission_requirements", ""),
                career_outcomes=values.get("career_outcomes", ""),
                accreditation=values.get("accreditation", "")[:255],
                program_url=values.get("program_url", "")[:1000],
                source_url=values.get("source_url", "")[:1000],
                is_higher_education_program=is_he,
                confidence_score=0.9,
                validation_status=ValidationStatus.NOT_VALIDATED,
                review_status=ReviewStatus.PENDING,
                raw_json={"manual": True},
                normalized_json={"manual_entry": True},
            )
            for field in MAJOR_REVIEW_FIELDS:
                _manual_evidence("program", major.pk, field, getattr(major, field), "Manual major staging entry.")
            messages.success(request, f"Added staged major {major.program_name}.")
            return redirect("academic_etl:program_detail", pk=major.pk)
    return render(request, "academic_etl/major_form.html", {
        "uni": uni,
        "fields": MAJOR_REVIEW_FIELDS,
        "degree_level_choices": DegreeLevel.choices,
    })


def evidence_detail(request, pk):
    ev = get_object_or_404(FieldEvidence, pk=pk)
    entity = None
    if ev.entity_type == "university":
        entity = ExtractedUniversity.objects.filter(pk=ev.entity_id).first()
    elif ev.entity_type == "program":
        entity = ExtractedProgram.objects.filter(pk=ev.entity_id).first()
    return render(request, "academic_etl/evidence_detail.html", {"ev": ev, "entity": entity})


def import_preview(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    approved_only = request.GET.get("all") != "1"
    threshold = settings.ETL_IMPORT_CONFIDENCE_THRESHOLD
    rows = []
    for uni in run.universities.order_by("name"):
        ok, reason = _eligible(uni, approved_only, threshold)
        existing, matched_by = (None, "")
        diff = {}
        if ok:
            existing, matched_by = _match_university(uni)
            diff = _diff_university(existing, uni)
        rows.append({
            "uni": uni, "eligible": ok, "reason": reason,
            "existing": existing, "matched_by": matched_by, "diff": diff,
            "action": ("update" if existing else "create") if ok else "skip",
            "n_programs": uni.programs.filter(review_status__in=["approved", "edited"]).count(),
        })
    return render(request, "academic_etl/import_preview.html", {
        "run": run, "rows": rows, "approved_only": approved_only,
        "threshold": threshold,
        "import_jobs": run.import_jobs.order_by("-created_at"),
    })


def import_job_detail(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)
    logs = job.logs.order_by("pk")
    action = request.GET.get("action")
    if action:
        logs = logs.filter(action=action)
    return render(request, "academic_etl/import_job_detail.html",
                  {"job": job, "logs": logs, "action_filter": action or ""})


# ---------------------------------------------------------------------------
# Fanar run
# ---------------------------------------------------------------------------
# Unified pipeline (single entry point)
# ---------------------------------------------------------------------------

@require_POST
def start_unified_run(request):
    """Single pipeline entry point. Two modes:
    - fast: Wikipedia discover -> AI fills ALL fields (~5 min for 200 unis)
    - thorough: Wikipedia discover -> crawl sites (5 parallel) -> AI gaps (~20 min)
    """
    if DataResetJob.active().exists():
        messages.error(request, "Data reset is active. Wait for it to finish before starting a run.")
        return redirect("academic_etl:dashboard")

    selected_country = request.POST.get("country", "").strip()
    custom_country = request.POST.get("custom_country", "").strip()
    country = custom_country if selected_country == "__custom__" else selected_country
    country_code = request.POST.get("country_code", "").strip()
    name, code = resolve_country(country, country_code)
    if not name:
        messages.error(request, "Choose a country or enter a custom country name.")
        return redirect("academic_etl:dashboard")

    mode = request.POST.get("mode", "fast")
    if mode not in {"fast", "thorough"}:
        mode = "fast"

    run = PipelineRun.objects.create(
        country_name=name, country_code=code,
        crawl_mode=mode, seed_provider="wikipedia",
        crawl_scope=f"unified_{mode}",
    )

    try:
        run_discovery(run, limit=0)
    except Exception as exc:
        run.status = PipelineRun.Status.FAILED
        run.error_message = str(exc)[:2000]
        run.save(update_fields=["status", "error_message", "updated_at"])
        messages.error(request, f"Run #{run.pk} discovery failed: {exc}")
        return redirect("academic_etl:run_detail", run_id=run.pk)

    valid = run.seeds.filter(status=InstitutionSeed.Status.VALID).count()

    token = claim_pipeline_run(run.pk)
    if token is None:
        messages.error(request, f"Run #{run.pk} already has an active worker.")
        return redirect("academic_etl:run_detail", run_id=run.pk)

    try:
        worker_pid = launch_unified_worker(run.pk, token)
    except OSError as exc:
        mark_failed(run.pk, token, exc)
        messages.error(request, f"Run #{run.pk} worker could not start: {exc}")
        return redirect("academic_etl:run_detail", run_id=run.pk)

    messages.success(
        request,
        f"Run #{run.pk} for {name}: {run.seeds.count()} seeds ({valid} valid). "
        f"Worker {worker_pid} started: crawl -> AI gap-fill -> validate.",
    )
    return redirect("academic_etl:run_detail", run_id=run.pk)


@require_POST
def resume_unified_run(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    if run.status != PipelineRun.Status.FAILED:
        messages.error(request, "Only a failed pipeline can be resumed.")
        return redirect("academic_etl:run_detail", run_id=run.pk)
    token = claim_pipeline_run(run.pk, allow_failed=True)
    if token is None:
        messages.error(request, f"Run #{run.pk} already has an active worker.")
        return redirect("academic_etl:run_detail", run_id=run.pk)
    try:
        worker_pid = launch_unified_worker(run.pk, token)
    except OSError as exc:
        mark_failed(run.pk, token, exc)
        messages.error(request, f"Run #{run.pk} worker could not restart: {exc}")
    else:
        messages.success(request, f"Run #{run.pk} resumed in worker {worker_pid}.")
    return redirect("academic_etl:run_detail", run_id=run.pk)


def run_unified_pipeline(run_id: int, worker_token: str = ""):
    """Execute one unified run with a host lock, checkpoints, and bounded retries."""
    if not worker_token:
        worker_token = claim_pipeline_run(run_id) or ""
        if not worker_token:
            return

    initial = PipelineRun.objects.get(pk=run_id)
    mode = (initial.crawl_scope or "").removeprefix("unified_") or "fast"
    if mode not in {"fast", "thorough"}:
        mode = "fast"
    logger = logging.getLogger("academic_etl.pipeline")
    host_lock = PipelineHostLock()
    heartbeat_stop = None
    heartbeat_thread = None

    def _run_stage(stage, label, status, callback):
        if not begin_stage(run_id, worker_token, stage, label, status):
            logger.info("Run #%d: checkpoint skips completed stage %s", run_id, stage)
            return
        logger.info("Run #%d: %s", run_id, label)
        callback(PipelineRun.objects.get(pk=run_id))
        complete_stage(run_id, worker_token, stage)

    def _progress(stage):
        def _update(**values):
            update_stage_progress(run_id, worker_token, stage, **values)
        return _update

    try:
        while not host_lock.acquire():
            if not owns_pipeline_run(run_id, worker_token):
                return
            check_cancelled(run_id, worker_token)
            heartbeat(
                run_id,
                worker_token,
                status=PipelineRun.Status.QUEUED,
                current_step="Queued behind another pipeline",
            )
            time.sleep(LOCK_POLL_SECONDS)

        heartbeat_stop = threading.Event()

        def _heartbeat_loop():
            interval = getattr(settings, "ETL_WORKER_HEARTBEAT_SECONDS", 15)
            while not heartbeat_stop.wait(interval):
                try:
                    heartbeat(run_id, worker_token)
                except Exception as exc:
                    logger.debug("Run #%d heartbeat failed: %s", run_id, exc)

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"pipeline-heartbeat-{run_id}",
            daemon=True,
        )
        heartbeat_thread.start()

        while True:
            try:
                _run_stage(
                    "wikipedia",
                    "Step 1/6: Wikipedia enrich",
                    PipelineRun.Status.CRAWLING,
                    lambda current: enrich_run_from_wikipedia(
                        current, progress_callback=_progress("wikipedia"),
                    ),
                )

                def _web_sources(current):
                    if mode == "thorough":
                        crawl_run(
                            current,
                            limit=0,
                            crawler=SiteCrawler(
                                max_pages=8,
                                country_code=current.country_code,
                            ),
                            concurrency=1,
                            progress_callback=_progress("web_sources"),
                        )
                    from .services.multi_source_scraper import enrich_run_from_web_sources

                    enrich_run_from_web_sources(
                        current,
                        concurrency=6,
                        progress_callback=_progress("web_sources"),
                    )

                _run_stage(
                    "web_sources",
                    "Step 2/6: Web scraping (QS, Wikipedia, official sites)",
                    PipelineRun.Status.CRAWLING,
                    _web_sources,
                )
                _run_stage(
                    "programs",
                    "Step 3/6: Crawling programs pages",
                    PipelineRun.Status.CRAWLING,
                    lambda current: _crawl_programs_only(
                        current, progress_callback=_progress("programs"),
                    ),
                )

                def _ai_fields(current):
                    if _test_ai_provider():
                        _ai_fill_gaps(
                            current,
                            use_cache=True,
                            progress_callback=_progress("ai_fields"),
                        )
                    else:
                        _progress("ai_fields")(
                            processed=1, total=1,
                            current_item="Fanar and Gemini unavailable",
                        )
                        logger.info(
                            "Run #%d: Fanar and Gemini unavailable; skipping quality enrichment",
                            run_id,
                        )

                _run_stage(
                    "ai_fields",
                    "Step 4/6: AI filling missing fields",
                    PipelineRun.Status.CRAWLING,
                    _ai_fields,
                )

                def _ai_majors(current):
                    if not _test_ai_provider():
                        _progress("ai_majors")(
                            processed=1, total=1, current_item="AI unavailable",
                        )
                        return
                    _extract_majors_for_run(
                        current,
                        progress_callback=_progress("ai_majors"),
                    )

                _run_stage(
                    "ai_majors",
                    "Step 5/6: Completing major coverage",
                    PipelineRun.Status.CRAWLING,
                    _ai_majors,
                )

                def _validate_and_finalize(current):
                    _progress("validation")(processed=0, total=1, current_item="Validating records")
                    _post_process_run(current)
                    validate_run(current)
                    if mode != "thorough":
                        _progress("validation")(
                            processed=1, total=1, current_item="Validation complete",
                        )
                        return
                    for seed in current.seeds.filter(status=InstitutionSeed.Status.VALID):
                        seed.raw_json = {
                            **(seed.raw_json or {}),
                            "crawl_terminal_reason": "No official-site crawl result",
                        }
                        seed.status = InstitutionSeed.Status.SKIPPED
                        seed.save(update_fields=["status", "raw_json"])
                    if current.seeds.filter(status=InstitutionSeed.Status.VALID).exists():
                        raise RuntimeError("Thorough run still has non-terminal valid seeds")
                    _progress("validation")(processed=1, total=1, current_item="Validation complete")

                _run_stage(
                    "validation",
                    "Step 6/6: Cleaning data & validating",
                    PipelineRun.Status.VALIDATING,
                    _validate_and_finalize,
                )
                mark_complete(run_id, worker_token)
                completed = PipelineRun.objects.get(pk=run_id)
                logger.info(
                    "Run #%d complete: %d universities, %d programs",
                    run_id,
                    completed.universities.count(),
                    completed.programs.count(),
                )
                return
            except PipelineCancelled:
                logger.info("Run #%d cancelled", run_id)
                mark_cancelled(run_id, worker_token)
                return
            except PipelineLeaseLost:
                logger.warning("Run #%d worker lease was replaced", run_id)
                return
            except Exception as exc:
                if is_recoverable_error(exc):
                    delay = mark_retrying(run_id, worker_token, exc)
                    if delay is not None:
                        logger.warning(
                            "Run #%d retrying in %ds after: %s",
                            run_id,
                            delay,
                            exc,
                        )
                        remaining = delay
                        while remaining > 0:
                            sleep_for = min(LOCK_POLL_SECONDS, remaining)
                            time.sleep(sleep_for)
                            remaining -= sleep_for
                            check_cancelled(run_id, worker_token)
                            heartbeat(
                                run_id,
                                worker_token,
                                status=PipelineRun.Status.RETRYING,
                            )
                        continue
                logger.exception("Pipeline fatal error for run #%d", run_id)
                mark_failed(run_id, worker_token, exc)
                return
    finally:
        if heartbeat_stop is not None:
            heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=1)
        host_lock.release()
        release_worker(run_id, worker_token)


def _test_ai_provider() -> bool:
    """Configuration check without spending an API request."""
    try:
        from .services.fanar_enrich import fanar_is_configured
        if fanar_is_configured():
            return True
    except Exception:
        pass
    try:
        from .services.gemini_enrich import is_configured
        if is_configured():
            return True
    except Exception:
        pass
    return False


def _ai_fill_gaps(run, use_cache=True, progress_callback=None):
    """Ask Fanar per missing field, then ground all unresolved fields once with Gemini."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .services.quality_enrichment import (
        apply_quality_result,
        apply_fanar_candidates,
        clear_unverified_quality_values,
        enrich_university_quality_hybrid,
        quality_fields_needed,
    )
    lgr = logging.getLogger("academic_etl.pipeline")

    universities = list(run.universities.select_related("seed").all())
    to_enrich = [(uni, quality_fields_needed(uni)) for uni in universities]
    to_enrich = [(uni, needed) for uni, needed in to_enrich if needed]
    for uni, needed in to_enrich:
        clear_unverified_quality_values(uni, needed)

    if not to_enrich:
        for uni in universities:
            if uni.sponsored is not False:
                uni.sponsored = False
                uni.save(update_fields=["sponsored"])
        lgr.info("Grounded quality enrichment: all fields already verified")
        return

    lgr.info(
        "Grounded quality enrichment: %d/%d universities need verification",
        len(to_enrich), len(universities),
    )
    filled_count = 0
    fail_count = 0
    handled_count = 0
    fanar_call_count = 0
    gemini_call_count = 0
    verified_field_count = 0
    if progress_callback:
        progress_callback(
            processed=0, total=len(to_enrich), fanar_calls=0,
            gemini_calls=0, verified_fields=0, errors=0,
        )

    def _fetch(uni, needed):
        return enrich_university_quality_hybrid(
            name=uni.name or (uni.seed.name if uni.seed else ""),
            country=run.country_name,
            country_code=run.country_code,
            city=uni.city or (uni.seed.city if uni.seed else ""),
            website=uni.website,
            needed=needed,
            use_cache=use_cache,
        )

    concurrency = max(1, min(getattr(settings, "FANAR_CONCURRENCY", 4), 8))
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_fetch, uni, needed): (uni, needed) for uni, needed in to_enrich}
        for f in as_completed(futures):
            uni, needed = futures[f]
            handled_count += 1
            try:
                result = f.result()
                fanar_call_count += result.get("fanar_calls", 0)
                gemini_call_count += result.get("gemini_calls", 0)
                fanar_candidates = result.get("fanar_candidates") or {}
                changed = apply_fanar_candidates(uni, fanar_candidates)
                remaining = set(result.get("remaining") or [])
                if remaining:
                    changed += apply_quality_result(
                        uni, remaining, result.get("gemini_result") or {},
                    )
                resolutions = (uni.normalized_json or {}).get("_quality_resolution") or {}
                verified_now = sum(
                    1 for field in needed
                    if (resolutions.get(field) or {}).get("status") in {"verified", "verified_absent"}
                )
                errors_now = len(needed) - verified_now
                verified_field_count += verified_now
                fail_count += errors_now
                if changed:
                    filled_count += 1
            except Exception as exc:
                fail_count += 1
                lgr.warning("Quality enrichment failed for %s: %s", uni.name, exc)
                apply_quality_result(uni, needed, {"error": str(exc)[:500]})
            if progress_callback:
                try:
                    progress_callback(
                        processed=handled_count,
                        total=len(to_enrich),
                        current_item=uni.name,
                        current_url=uni.website,
                        enriched=filled_count,
                        errors=fail_count,
                        fanar_calls=fanar_call_count,
                        gemini_calls=gemini_call_count,
                        verified_fields=verified_field_count,
                    )
                except Exception:
                    for pending in futures:
                        pending.cancel()
                    raise

    lgr.info("Grounded quality enrichment complete: %d updated, %d failed", filled_count, fail_count)


def _crawl_programs_only(run, progress_callback=None):
    """Extract programs from official website (primary) + Wikipedia (supplement).
    Website crawl is authoritative; Wikipedia adds departments the site missed."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from django.db import OperationalError
    from time import sleep
    from .services.crawler import get_with_http_fallback
    from .services.wikipedia_extract import extract_programs_from_wikipedia
    from .services.extraction import extract_programs
    lgr = logging.getLogger("academic_etl.pipeline")

    universities = list(run.universities.select_related("seed").all())
    if not universities:
        return

    lgr.info("Programs extraction: %d universities", len(universities))
    existing_programs = run.programs.count()
    total_progs = [0]
    processed = [0]
    errors = [0]
    if progress_callback:
        progress_callback(processed=0, total=len(universities), programs=existing_programs)

    def _save_progress(done=False):
        run.total_programs_found = existing_programs + total_progs[0]
        run.worker_heartbeat_at = timezone.now()
        run.stats_json = {
            **run.stats_json,
            "programs_crawl": {
                "processed": processed[0],
                "total": len(universities),
                "created": total_progs[0],
                "programs": run.total_programs_found,
                "errors": errors[0],
                "done": done,
            },
        }
        for attempt in range(3):
            try:
                run.save(update_fields=[
                    "stats_json", "total_programs_found",
                    "worker_heartbeat_at", "updated_at",
                ])
                return
            except OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                if attempt == 2:
                    lgr.warning("Could not persist programs-crawl progress: %s", exc)
                    return
                sleep(0.25 * (attempt + 1))

    _save_progress(done=False)

    def _extract_one(uni):
        seed = uni.seed
        seen_names = set()
        programs = []

        # Source 1: Official website crawl (primary — real program data from the university)
        if uni.website:
            try:
                from urllib.parse import urljoin
                from bs4 import BeautifulSoup
                import requests as req
                headers = {"User-Agent": "BeyondDegreeBot/0.1"}
                resp = get_with_http_fallback(
                    req, uni.website, headers=headers, timeout=10, allow_redirects=True,
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    pages = [{"soup": soup, "url": uni.website, "final_url": resp.url,
                              "page_type": "homepage", "title": ""}]

                    visited = {resp.url}
                    for a in soup.find_all("a", href=True):
                        if len(pages) >= 5:
                            break
                        href_lower = a["href"].lower()
                        if any(kw in href_lower for kw in
                               ["program", "academic", "department", "course",
                                "faculty", "school-of", "college-of", "study"]):
                            try:
                                full = urljoin(resp.url, a["href"])
                                if full in visited:
                                    continue
                                visited.add(full)
                                r2 = get_with_http_fallback(
                                    req, full, headers=headers, timeout=8, allow_redirects=True,
                                )
                                if r2.status_code == 200:
                                    s2 = BeautifulSoup(r2.text, "html.parser")
                                    pages.append({"soup": s2, "url": full, "final_url": r2.url,
                                                  "page_type": "programs", "title": ""})
                            except Exception:
                                pass

                    for prog in extract_programs(pages):
                        name = (prog.get("program_name") or "").strip()
                        if not name or name.lower() in seen_names:
                            continue
                        seen_names.add(name.lower())
                        degree = prog.get("degree_level", "unknown")
                        if hasattr(degree, "value"):
                            degree = degree.value
                        programs.append({
                            "program_name": name[:500],
                            "degree_level": str(degree),
                            "defaults": {
                                "is_higher_education_program": prog.get("is_higher_education_program", True),
                                "confidence_score": prog.get("confidence", 0.6),
                                "program_url": prog.get("program_url", ""),
                                "source_url": uni.website,
                                "country": run.country_name,
                                "country_code": run.country_code,
                                "university_slug": uni.slug,
                            },
                        })
            except Exception:
                pass

        # Source 2: Wikipedia sections (supplement — adds departments website missed)
        _FACULTY_RE = re.compile(
            r"^(school of|faculty of|department of|centre for|center for|"
            r"division of|college of|institute of|khoa |bộ môn )",
            re.IGNORECASE,
        )
        wiki_url = seed.wikipedia_url if seed else ""
        if wiki_url:
            try:
                wiki_progs = extract_programs_from_wikipedia(wiki_url)
                for wp in wiki_progs:
                    name = (wp.get("program_name") or "").strip()
                    if not name or name.lower() in seen_names:
                        continue
                    if _FACULTY_RE.match(name):
                        continue
                    if len(name.split()) <= 3 and not re.search(
                        r"\b(B\.|M\.|Ph\.?D|MBA|BBA|BCA|MCA|MBBS|LLB|LLM|"
                        r"B\.Tech|M\.Tech|B\.Sc|M\.Sc|B\.A|M\.A|B\.Com|M\.Com)\b",
                        name, re.IGNORECASE,
                    ):
                        continue
                    seen_names.add(name.lower())
                    programs.append({
                        "program_name": name[:500],
                        "degree_level": "bachelor",
                        "defaults": {
                            "faculty_or_school": wp.get("faculty_or_school", ""),
                            "program_url": wp.get("program_url", ""),
                            "is_higher_education_program": True,
                            "confidence_score": 0.65,
                            "country": run.country_name,
                            "country_code": run.country_code,
                            "university_slug": uni.slug,
                            "source_url": uni.website or wiki_url,
                        },
                    })
            except Exception:
                pass

        return programs

    def _save_programs(uni, programs):
        created_count = 0
        for program in programs:
            _, created = ExtractedProgram.objects.get_or_create(
                pipeline_run=run,
                extracted_university=uni,
                program_name=program["program_name"],
                degree_level=program["degree_level"],
                defaults=program["defaults"],
            )
            if created:
                created_count += 1
        return created_count

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_extract_one, uni): uni for uni in universities}
        for f in as_completed(futures):
            university = futures[f]
            try:
                n = _save_programs(university, f.result() or [])
                total_progs[0] += n
                processed[0] += 1
                if processed[0] % 10 == 0 or processed[0] == len(universities):
                    _save_progress(done=False)
            except Exception:
                processed[0] += 1
                errors[0] += 1
                if processed[0] % 10 == 0 or processed[0] == len(universities):
                    _save_progress(done=False)
            if progress_callback:
                try:
                    progress_callback(
                        processed=processed[0],
                        total=len(universities),
                        current_item=university.name,
                        current_url=university.website,
                        programs=existing_programs + total_progs[0],
                        errors=errors[0],
                    )
                except Exception:
                    for pending in futures:
                        pending.cancel()
                    raise
            if processed[0] % 20 == 0:
                lgr.info("Programs: %d/%d universities, %d programs found",
                         processed[0], len(universities), total_progs[0])

    _save_progress(done=True)
    lgr.info("Programs complete: %d programs from %d universities",
             total_progs[0], len(universities))


def _post_process_run(run):
    """Clean data quality: remove junk, fix formats, set defaults."""
    from .services.classification import is_junk_entry
    from .services.country_registry import get_numeric_code
    from .services.financial import standardize_financials
    from .services.quality_enrichment import (
        clear_unverified_fanar_campus_count,
        downgrade_ungrounded_quality_errors,
    )

    numeric_code = get_numeric_code(run.country_code)
    logger = logging.getLogger("academic_etl.pipeline")
    removed = 0
    fixed = 0

    for uni in run.universities.all():
        if is_junk_entry(uni.name):
            uni.delete()
            removed += 1
            continue

        changed = False

        # Legacy Fanar campus lists had no source requirement and could include
        # affiliated colleges or regional offices. Do not retain an invented count.
        if clear_unverified_fanar_campus_count(uni):
            changed = True
        if downgrade_ungrounded_quality_errors(uni):
            changed = True

        # Location = ISO numeric code
        if numeric_code and uni.location != numeric_code:
            uni.location = numeric_code
            changed = True

        # Crawled catalog records are never paid placements.
        if uni.sponsored is not False:
            uni.sponsored = False
            changed = True

        # Boolean defaults
        for bf in ("student_loan_available", "housing_availability", "immigration_support"):
            if getattr(uni, bf) is None:
                setattr(uni, bf, False)
                changed = True

        # Standardize financials format
        if uni.financials and not uni.financials_currency:
            std = standardize_financials(uni.financials, country_code=run.country_code)
            if std.get("formatted"):
                uni.financials = std["formatted"]
                uni.financials_currency = std.get("currency", "")
                uni.financials_amount_low = std.get("amount_low")
                uni.financials_amount_high = std.get("amount_high")
                uni.financials_usd_low = std.get("usd_low")
                uni.financials_usd_high = std.get("usd_high")
                changed = True

        # Store contact data in one canonical format. Invalid AI/source output
        # (including academic years) becomes empty rather than looking real.
        normalized_phone = normalize_phone(uni.admissions_phone)
        if uni.admissions_phone != normalized_phone:
            uni.admissions_phone = normalized_phone
            changed = True
        normalized_email = normalize_email(uni.admissions_contact)
        if uni.admissions_contact != normalized_email:
            uni.admissions_contact = normalized_email
            changed = True
        for field in UNIVERSITY_URL_FIELDS:
            current_url = getattr(uni, field)
            normalized_url = normalize_url(current_url)
            if current_url != normalized_url:
                setattr(uni, field, normalized_url)
                changed = True

        if changed:
            uni.save()
            fixed += 1

    logger.info("Post-process: removed %d junk, fixed %d records", removed, fixed)
    return {"removed": removed, "fixed": fixed}


def _extract_majors_for_run(run, progress_callback=None):
    """Extract majors/programs for all universities via LLM. Concurrent 5 workers."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .services.llm_provider import enrich_majors, get_active_provider
    lgr = logging.getLogger("academic_etl.pipeline")

    if not get_active_provider():
        lgr.info("No LLM provider — skipping majors extraction")
        return

    universities = [u for u in run.universities.exclude(name="").order_by("pk") if u.programs.count() < 5]
    if not universities:
        lgr.info("Majors: all universities already have sufficient programs")
        return

    lgr.info("Majors extraction: %d universities to process", len(universities))
    total_programs = [0]
    fail_count = [0]
    handled_count = [0]
    if progress_callback:
        progress_callback(processed=0, total=len(universities))

    def _extract_one(uni):
        try:
            majors, provider = enrich_majors(name=uni.name, country=run.country_name, country_code=run.country_code)
        except Exception:
            return 0
        if not majors:
            return 0
        count = 0
        for major in majors:
            prog_name = (major.get("program_name") or "").strip()
            if not prog_name:
                continue
            degree = (major.get("degree_level") or "unknown").lower()
            if degree not in {d.value for d in DegreeLevel}:
                degree = "unknown"

            prog, created = ExtractedProgram.objects.get_or_create(
                pipeline_run=run, extracted_university=uni,
                program_name=prog_name, degree_level=degree,
                defaults={
                    "faculty_or_school": major.get("faculty_or_school", ""),
                    "field_of_study": major.get("field_of_study", ""),
                    "duration": major.get("duration", ""),
                    "tuition_fee": major.get("tuition_fee", ""),
                    "program_url": major.get("program_url", ""),
                    "country": run.country_name,
                    "country_code": run.country_code,
                    "university_slug": uni.slug,
                    "is_higher_education_program": degree in ("bachelor", "master", "phd",
                        "postgraduate_certificate", "postgraduate_diploma", "professional"),
                    "confidence_score": 0.75,
                },
            )
            if created:
                count += 1

            for spec_name in major.get("specializations", []):
                if spec_name and spec_name.strip():
                    ExtractedSpecialization.objects.get_or_create(
                        pipeline_run=run, extracted_program=prog,
                        specialization_name=spec_name.strip(),
                        defaults={"confidence_score": 0.70},
                    )
        return count

    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = {pool.submit(_extract_one, uni): uni for uni in universities}
        for f in as_completed(futures):
            university = futures[f]
            handled_count[0] += 1
            try:
                n = f.result()
                if n:
                    total_programs[0] += n
                    if total_programs[0] % 20 == 0:
                        lgr.info("Majors: %d programs extracted so far", total_programs[0])
                else:
                    fail_count[0] += 1
                    if fail_count[0] >= 3:
                        lgr.info("Majors: 3 failures, stopping")
                        pool.shutdown(wait=False, cancel_futures=True)
                        break
            except Exception:
                fail_count[0] += 1
            if progress_callback:
                try:
                    progress_callback(
                        processed=handled_count[0],
                        total=len(universities),
                        current_item=university.name,
                        current_url=university.website,
                        programs=total_programs[0],
                        errors=fail_count[0],
                    )
                except Exception:
                    for pending in futures:
                        pending.cancel()
                    raise

    lgr.info("Majors extraction complete: %d programs for %d universities",
             total_programs[0], len(universities))


# ---------------------------------------------------------------------------
# Global university & major workspaces
# ---------------------------------------------------------------------------

def global_universities(request):
    """All universities across ALL pipeline runs."""
    qs = ExtractedUniversity.objects.select_related("pipeline_run").order_by("-confidence_score")
    q = request.GET.get("q", "")
    country = request.GET.get("country", "")
    validation = request.GET.get("validation", "")
    review = request.GET.get("review", "")

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(website__icontains=q) | Q(slug__icontains=q))
    if country:
        qs = qs.filter(Q(country__icontains=country) | Q(country_code=country.upper()))
    if validation:
        qs = qs.filter(validation_status=validation)
    if review:
        qs = qs.filter(review_status=review)

    from django.core.paginator import Paginator
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(request, "academic_etl/global_universities.html", {
        "page": page,
        "q": q, "country": country, "validation": validation, "review": review,
        "total_count": ExtractedUniversity.objects.count(),
        "countries": list(ExtractedUniversity.objects.exclude(country="").values_list("country", flat=True).distinct().order_by("country")),
        "validation_choices": ValidationStatus.choices,
        "review_choices": ReviewStatus.choices,
    })


def global_majors(request):
    """All majors across ALL pipeline runs."""
    qs = ExtractedProgram.objects.select_related("extracted_university", "pipeline_run").order_by("-confidence_score")
    q = request.GET.get("q", "")
    country = request.GET.get("country", "")
    degree = request.GET.get("degree", "")
    validation = request.GET.get("validation", "")

    if q:
        qs = qs.filter(Q(program_name__icontains=q) | Q(extracted_university__name__icontains=q))
    if country:
        qs = qs.filter(Q(country__icontains=country) | Q(country_code=country.upper()))
    if degree:
        qs = qs.filter(degree_level=degree)
    if validation:
        qs = qs.filter(validation_status=validation)

    from django.core.paginator import Paginator
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(request, "academic_etl/global_majors.html", {
        "page": page,
        "q": q, "country": country, "degree": degree, "validation": validation,
        "total_count": ExtractedProgram.objects.count(),
        "countries": list(ExtractedProgram.objects.exclude(country="").values_list("country", flat=True).distinct().order_by("country")),
        "degree_choices": DegreeLevel.choices,
        "validation_choices": ValidationStatus.choices,
    })


# ---------------------------------------------------------------------------
# Fanar run (legacy, kept for backward compat)
# ---------------------------------------------------------------------------

@require_POST
def start_fanar_run(request):
    selected_country = request.POST.get("country", "").strip()
    custom_country = request.POST.get("custom_country", "").strip()
    country = custom_country if selected_country == "__custom__" else selected_country
    country_code = request.POST.get("country_code", "").strip()
    name, code = resolve_country(country, country_code)
    if not name:
        messages.error(request, "Choose a country or enter a custom country name.")
        return redirect("academic_etl:dashboard")

    discover_limit = _positive_int(request.POST.get("discover_limit"), 0, 500)
    with_majors = request.POST.get("with_majors", "0") == "1"
    use_fallback = request.POST.get("fallback", "1") == "1"

    run = PipelineRun.objects.create(
        country_name=name, country_code=code,
        crawl_mode="full", seed_provider="wikipedia",
        crawl_scope="fanar_enrichment",
    )

    def _bg_fanar():
        from .services.fanar_enrich import enrich_institution_fanar, enrich_majors_fanar, fanar_is_configured
        from .services.normalize import normalize_url as norm_url
        from .services.validation import validate_run as val_run

        try:
            run_discovery(run, limit=discover_limit)
            valid_seeds = run.seeds.filter(status=InstitutionSeed.Status.VALID)

            for seed in valid_seeds.iterator():
                # Try Fanar first, then Gemini fallback
                result = {}
                provider = ""
                if fanar_is_configured():
                    try:
                        result = enrich_institution_fanar(
                            name=seed.name, country=name, country_code=code,
                            city=seed.city, wikipedia_url=seed.wikipedia_url,
                        )
                        provider = "fanar"
                    except Exception:
                        pass

                if not result and use_fallback and gemini_is_configured():
                    try:
                        from .services.llm_provider import enrich_institution
                        result, provider = enrich_institution(
                            name=seed.name, country=name, country_code=code,
                            city=seed.city, wikipedia_url=seed.wikipedia_url,
                        )
                    except Exception:
                        pass

                if not result:
                    continue

                uni, _ = ExtractedUniversity.objects.update_or_create(
                    pipeline_run=run, seed=seed,
                    defaults={
                        "name": result.get("name") or seed.name,
                        "website": norm_url(result.get("website", "")),
                        "description": result.get("description", ""),
                        "campus_student_life": result.get("campus_student_life", ""),
                        "number_of_students": result.get("number_of_students"),
                        "financials": result.get("financials", ""),
                        "global_rank": result.get("global_rank", ""),
                        "student_to_faculty_ratio": result.get("student_to_faculty_ratio", ""),
                        "admissions_contact": result.get("admissions_contact", ""),
                        "admissions_phone": result.get("admissions_phone", ""),
                        "admissions_page_link": result.get("admissions_page_link", ""),
                        "country": name, "country_code": code,
                        "city": seed.city, "region": seed.region,
                        "institution_type": seed.institution_type,
                        "slug": make_slug(result.get("name") or seed.name, seed.city),
                        "confidence_score": 0.80,
                    },
                )

                now = timezone.now()
                for field_name in ("name", "website", "description", "campus_student_life",
                                   "number_of_students", "financials", "global_rank"):
                    val = result.get(field_name)
                    if val is not None and val != "":
                        FieldEvidence.objects.create(
                            entity_type="university", entity_id=uni.pk,
                            field_name=field_name, extracted_value=str(val),
                            normalized_value=str(val),
                            source_url=f"{provider}-api:{seed.name}",
                            page_type=f"{provider}_enrichment",
                            confidence_score=0.80,
                            extractor_name=f"{provider}_chat",
                            extraction_method=f"{provider}_enrichment",
                            crawled_at=now,
                        )

                if with_majors:
                    majors = []
                    if provider == "fanar":
                        try:
                            majors = enrich_majors_fanar(name=uni.name, country=name, country_code=code)
                        except Exception:
                            pass
                    if not majors and use_fallback:
                        from .services.llm_provider import enrich_majors as llm_majors
                        majors, _ = llm_majors(name=uni.name, country=name, country_code=code)

                    for major in majors:
                        prog_name = major.get("program_name", "").strip()
                        if not prog_name:
                            continue
                        degree = major.get("degree_level", "unknown").lower()
                        if degree not in {d.value for d in DegreeLevel}:
                            degree = "unknown"
                        prog, _ = ExtractedProgram.objects.get_or_create(
                            pipeline_run=run, extracted_university=uni,
                            program_name=prog_name, degree_level=degree,
                            defaults={
                                "faculty_or_school": major.get("faculty_or_school", ""),
                                "field_of_study": major.get("field_of_study", ""),
                                "duration": major.get("duration", ""),
                                "tuition_fee": major.get("tuition_fee", ""),
                                "program_url": major.get("program_url", ""),
                                "country": name, "country_code": code,
                                "university_slug": uni.slug,
                                "is_higher_education_program": True,
                                "confidence_score": 0.75,
                            },
                        )
                        for spec_name in major.get("specializations", []):
                            if spec_name and spec_name.strip():
                                ExtractedSpecialization.objects.get_or_create(
                                    pipeline_run=run, extracted_program=prog,
                                    specialization_name=spec_name.strip(),
                                    defaults={"confidence_score": 0.70},
                                )

                seed.status = InstitutionSeed.Status.CRAWLED
                seed.save(update_fields=["status"])

            val_run(run)
            run.status = PipelineRun.Status.REVIEW
            run.total_crawled_institutions = run.universities.count()
            run.total_programs_found = run.programs.count()
            run.save(update_fields=["status", "total_crawled_institutions", "total_programs_found"])

        except Exception as exc:
            run.status = PipelineRun.Status.FAILED
            run.error_message = str(exc)
            run.save(update_fields=["status", "error_message"])

    thread = threading.Thread(target=_bg_fanar, daemon=True)
    thread.start()
    messages.success(request, f"Run #{run.pk} started for {name} with Fanar enrichment (background).")
    return redirect("academic_etl:run_detail", run.pk)


# ---------------------------------------------------------------------------
# Schedules management
# ---------------------------------------------------------------------------

def schedules_list(request):
    schedules = CrawlSchedule.objects.order_by("country_name")
    return render(request, "academic_etl/schedules_list.html", {
        "schedules": schedules,
        "country_options": _get_country_options(),
    })


@require_POST
def schedule_create(request):
    country = request.POST.get("country", "").strip()
    name, code = resolve_country(country)
    if not name or not code:
        messages.error(request, "Cannot resolve country.")
        return redirect("academic_etl:schedules_list")

    CrawlSchedule.objects.update_or_create(
        country_code=code,
        defaults={
            "country_name": name,
            "frequency": request.POST.get("frequency", "monthly"),
            "strategy": request.POST.get("strategy", "hybrid"),
            "discover_limit": _positive_int(request.POST.get("discover_limit"), 200, 1000),
            "is_active": True,
        },
    )
    messages.success(request, f"Schedule for {name} saved.")
    return redirect("academic_etl:schedules_list")


@require_POST
def schedule_toggle(request, pk):
    schedule = get_object_or_404(CrawlSchedule, pk=pk)
    action = request.POST.get("action", "")
    if action == "disable":
        schedule.is_active = False
    elif action == "enable":
        schedule.is_active = True
        schedule.error_count = 0
    schedule.save()
    messages.success(request, f"Schedule for {schedule.country_name} {'enabled' if schedule.is_active else 'paused'}.")
    return redirect("academic_etl:schedules_list")


@require_POST
def schedule_delete(request, pk):
    schedule = get_object_or_404(CrawlSchedule, pk=pk)
    name = schedule.country_name
    schedule.delete()
    messages.success(request, f"Schedule for {name} deleted.")
    return redirect("academic_etl:schedules_list")


# ---------------------------------------------------------------------------
# Country configs
# ---------------------------------------------------------------------------

def country_configs_list(request):
    configs = CountryConfig.objects.order_by("country_name")
    return render(request, "academic_etl/country_configs_list.html", {
        "configs": configs,
        "active_count": configs.filter(is_active=True).count(),
        "currency_count": configs.values("currency_code").distinct().count(),
    })


# ---------------------------------------------------------------------------
# Specializations
# ---------------------------------------------------------------------------

def specializations_list(request, run_id):
    run = get_object_or_404(PipelineRun, pk=run_id)
    specs = ExtractedSpecialization.objects.filter(pipeline_run=run).select_related(
        "extracted_program", "extracted_program__extracted_university",
    ).order_by("extracted_program__extracted_university__name", "extracted_program__program_name", "specialization_name")

    q = request.GET.get("q", "")
    review = request.GET.get("review", "")
    if q:
        specs = specs.filter(specialization_name__icontains=q)
    if review:
        specs = specs.filter(review_status=review)

    return render(request, "academic_etl/specializations_list.html", {
        "run": run,
        "specializations": specs,
        "total": ExtractedSpecialization.objects.filter(pipeline_run=run).count(),
        "approved_count": ExtractedSpecialization.objects.filter(pipeline_run=run, review_status="approved").count(),
        "pending_count": ExtractedSpecialization.objects.filter(pipeline_run=run, review_status="pending").count(),
        "q": q,
        "review": review,
    })


@require_POST
def specialization_action(request, pk):
    spec = get_object_or_404(ExtractedSpecialization, pk=pk)
    action = request.POST.get("action", "")
    if action == "approve":
        spec.review_status = ReviewStatus.APPROVED
    elif action == "reject":
        spec.review_status = ReviewStatus.REJECTED
    spec.save(update_fields=["review_status", "updated_at"])

    next_url = request.POST.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("academic_etl:specializations_list", spec.pipeline_run_id)


# ---------------------------------------------------------------------------
# Data management (clear/delete)
# ---------------------------------------------------------------------------

@require_POST
def clear_staging(request):
    from .services.data_reset import request_data_reset

    job, created = request_data_reset(DataResetJob.Mode.STAGING)
    message = f"Staging reset job #{job.pk} started." if created else f"Reset job #{job.pk} is already active."
    messages.success(request, message)
    return redirect("academic_etl:dashboard")


@require_POST
def clear_production(request):
    from .services.data_reset import request_data_reset

    job, created = request_data_reset(DataResetJob.Mode.PRODUCTION)
    message = f"Production reset job #{job.pk} started." if created else f"Reset job #{job.pk} is already active."
    messages.success(request, message)
    return redirect("academic_etl:dashboard")


@require_POST
def clear_all(request):
    from .services.data_reset import request_data_reset

    job, created = request_data_reset(DataResetJob.Mode.ALL)
    message = f"Full reset job #{job.pk} started." if created else f"Reset job #{job.pk} is already active."
    messages.success(request, message)
    return redirect("academic_etl:dashboard")
