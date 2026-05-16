import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.clean_record import CleanRecord
from app.models.clean_template import CleanTemplate
from app.models.crawl_job import CrawlJob
from app.models.data_source import DataSource
from app.models.ai_extraction_log import AIExtractionLog
from app.models.raw_record import RawRecord
from app.models.review_action import ReviewAction
from app.schemas.crawl_job import (
    CrawlJobCreate,
    CrawlJobCreateResponse,
    CrawlJobDetailResponse,
    CrawlJobListItem,
    CrawlJobListResponse,
    CrawlJobProgress,
    CrawlJobQualitySummary,
)
from app.schemas.crawl_run import CrawlJobRunResponse
from app.services.direct_run import run_crawl_job_direct
from app.services.source_registry import (
    build_trusted_source_discovery_input,
    has_trusted_source_plan,
    source_names_from_discovery_input,
)
from app.services.supplemental_registry import (
    build_supplemental_discovery_input,
    has_supplemental_coverage_plan,
    supplemental_source_names_from_discovery_input,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crawl-jobs", tags=["crawl-jobs"])

PROCESSING_STATUSES = {"CRAWLING", "EXTRACTING", "CLEANING"}
STALE_PROCESSING_AFTER = timedelta(minutes=5)


def _default_progress() -> dict[str, int]:
    return {
        "total_records": 0,
        "crawled": 0,
        "extracted": 0,
        "needs_review": 0,
        "cleaned": 0,
        "skipped": 0,
        "clean_candidates": 0,
        "approved": 0,
        "rejected": 0,
        "processed": 0,
    }


def _aware_datetime(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_stale_processing_job(job: CrawlJob) -> bool:
    if getattr(job, "status", None) not in PROCESSING_STATUSES:
        return False
    updated_at = _aware_datetime(getattr(job, "updated_at", None))
    if updated_at is None:
        return False
    return datetime.now(timezone.utc) - updated_at > STALE_PROCESSING_AFTER


def _source_names_by_id(db: Session, source_ids: list[str]) -> dict[str, str]:
    if not source_ids:
        return {}
    sources = db.query(DataSource).filter(DataSource.id.in_(source_ids)).all()
    return {str(source.id): source.source_name for source in sources}


def _planned_source_names(discovery_input: dict[str, object] | None) -> list[str]:
    planned_names = source_names_from_discovery_input(discovery_input)
    if planned_names:
        return planned_names
    return supplemental_source_names_from_discovery_input(discovery_input)


def _source_names_for_job(db: Session, job: CrawlJob) -> list[str]:
    source_name_map = _source_names_by_id(db, job.source_ids)
    persisted_names = [source_name_map.get(source_id, source_id) for source_id in job.source_ids]
    if persisted_names:
        return persisted_names
    return _planned_source_names(getattr(job, "discovery_input", None))


def _resolved_discovery_input(payload: CrawlJobCreate) -> dict[str, object]:
    discovery_input = payload.resolved_discovery_input()
    if payload.crawl_mode == "trusted_sources":
        if payload.source_ids:
            return discovery_input
        if not has_trusted_source_plan(payload.country):
            raise HTTPException(status_code=400, detail=f"No trusted-source plan is configured for {payload.country}")
        return build_trusted_source_discovery_input(payload.country)
    if payload.crawl_mode == "supplemental_discovery":
        if discovery_input.get("supplemental_plan"):
            return discovery_input
        if not has_supplemental_coverage_plan(payload.country):
            raise HTTPException(status_code=400, detail=f"No supplemental coverage plan is configured for {payload.country}")
        return build_supplemental_discovery_input(payload.country)
    return discovery_input


def _trusted_sources_for_payload(db: Session, payload: CrawlJobCreate) -> list[DataSource]:
    if payload.crawl_mode != "trusted_sources" or not payload.source_ids:
        return []
    return db.query(DataSource).filter(DataSource.id.in_(payload.source_ids)).all()


def _validate_trusted_sources(payload: CrawlJobCreate, sources: list[DataSource]) -> None:
    if payload.crawl_mode == "trusted_sources":
        if payload.source_ids and len(sources) != len(set(payload.source_ids)):
            raise HTTPException(status_code=400, detail="One or more source_ids are invalid")
        if not payload.source_ids and not has_trusted_source_plan(payload.country):
            raise HTTPException(status_code=400, detail=f"No trusted-source plan is configured for {payload.country}")
        return
    if payload.crawl_mode == "supplemental_discovery":
        discovery_input = payload.resolved_discovery_input()
        if discovery_input.get("supplemental_plan"):
            return
        if not has_supplemental_coverage_plan(payload.country):
            raise HTTPException(status_code=400, detail=f"No supplemental coverage plan is configured for {payload.country}")


def _source_ids_for_job(payload: CrawlJobCreate, discovery_input: dict[str, object]) -> list[str]:
    del discovery_input
    return list(payload.source_ids)


def _list_item_template_name(db: Session, template_id: str) -> str | None:
    template = db.query(CleanTemplate).filter(CleanTemplate.id == template_id).one_or_none()
    return template.template_name if template is not None else None


def _job_template(db: Session, template_id: str):
    return db.query(CleanTemplate).filter(CleanTemplate.id == template_id).one_or_none()


def _template_column_names(template: CleanTemplate | object | None) -> list[str]:
    columns = getattr(template, "columns", None)
    if not isinstance(columns, list):
        return []
    names: list[str] = []
    for column in sorted(columns, key=lambda item: item.get("order", 0) if isinstance(item, dict) else 0):
        if not isinstance(column, dict):
            continue
        name = str(column.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _discovery_input_for_response(job: CrawlJob) -> dict[str, object] | None:
    value = getattr(job, "discovery_input", None)
    return value if isinstance(value, dict) else None


def _crawl_mode_for_job(job: CrawlJob) -> str:
    return getattr(job, "crawl_mode", "trusted_sources")


def _job_source_ids(job: CrawlJob) -> list[str]:
    return list(getattr(job, "source_ids", []) or [])


def _critical_fields_for_job(job: CrawlJob) -> list[str] | None:
    fields = getattr(job, "critical_fields", None)
    return list(fields) if isinstance(fields, list) else fields


def _validate_focus_fields_against_template(fields: list[str], template: CleanTemplate | object | None) -> None:
    template_fields = set(_template_column_names(template))
    if not template_fields:
        return
    invalid_fields = [field for field in fields if field not in template_fields]
    if invalid_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Focus fields must come from the selected template columns: {', '.join(invalid_fields)}",
        )


def _source_names_from_jobs(db: Session, jobs: list[CrawlJob]) -> dict[str, list[str]]:
    source_name_map = _source_names_by_id(db, [source_id for job in jobs for source_id in _job_source_ids(job)])
    return {
        str(job.id): [source_name_map.get(source_id, source_id) for source_id in _job_source_ids(job)]
        if _job_source_ids(job)
        else _planned_source_names(_discovery_input_for_response(job))
        for job in jobs
    }


def _quality_summary(db: Session, job_id: str) -> CrawlJobQualitySummary:
    clean_records = db.query(CleanRecord).filter(CleanRecord.job_id == job_id).all()
    clean_count = len(clean_records)
    approved_count = sum(1 for record in clean_records if record.status == "APPROVED")
    needs_review_count = sum(1 for record in clean_records if record.status == "NEEDS_REVIEW")
    rejected_count = sum(1 for record in clean_records if record.status == "REJECTED")
    quality_scores = [record.quality_score for record in clean_records if record.quality_score is not None]
    quality_score = round(sum(quality_scores) / len(quality_scores)) if quality_scores else None
    return CrawlJobQualitySummary(
        clean_candidates=clean_count,
        approved_count=approved_count,
        needs_review_count=needs_review_count,
        rejected_count=rejected_count,
        quality_score=quality_score,
    )


def _progress_for_response(job: CrawlJob) -> CrawlJobProgress:
    progress_payload = dict(_default_progress())
    progress_payload.update(getattr(job, "progress", {}) or {})
    return CrawlJobProgress(**progress_payload)


def _clean_counts_for_response(db: Session, job_id: str) -> tuple[int, CrawlJobQualitySummary]:
    summary = _quality_summary(db, job_id)
    return summary.clean_candidates, summary


def _create_response_from_progress(job: CrawlJob) -> CrawlJobCreateResponse:
    progress = _progress_for_response(job)
    return CrawlJobCreateResponse(
        job_id=str(job.id),
        status="CRAWLING",
        message="Job created. Processing is running in the background.",
        crawl_mode=job.crawl_mode,
        discovery_input=job.discovery_input,
        total_records=progress.total_records,
        crawled=progress.crawled,
        extracted=progress.extracted,
        needs_review=progress.needs_review,
        cleaned=progress.cleaned,
        skipped=progress.skipped,
        clean_candidates=progress.clean_candidates,
        approved=progress.approved,
        rejected=progress.rejected,
    )


def _run_response_from_progress(job: CrawlJob, *, message: str) -> CrawlJobRunResponse:
    progress = _progress_for_response(job)
    return CrawlJobRunResponse(
        job_id=str(job.id),
        status=job.status,
        total_records=progress.total_records,
        crawled=progress.crawled,
        extracted=progress.extracted,
        needs_review=progress.needs_review,
        cleaned=progress.cleaned,
        message=message,
    )


class CrawlJobDeleteResponse(BaseModel):
    job_id: str
    status: str
    message: str
    deleted_raw_records: int
    deleted_ai_logs: int
    deleted_clean_records: int
    deleted_review_actions: int


@router.get("", response_model=CrawlJobListResponse)
def list_crawl_jobs(db: Session = Depends(get_db)) -> CrawlJobListResponse:
    jobs = db.query(CrawlJob).order_by(CrawlJob.updated_at.desc()).all()
    source_names_by_job = _source_names_from_jobs(db, jobs)

    items: list[CrawlJobListItem] = []
    for job in jobs:
        clean_count, quality_summary = _clean_counts_for_response(db, str(job.id))
        progress = _progress_for_response(job)
        items.append(
            CrawlJobListItem(
                job_id=str(job.id),
                country=job.country,
                status=job.status,
                source_names=source_names_by_job.get(str(job.id), []),
                template_name=_list_item_template_name(db, job.clean_template_id),
                crawl_mode=_crawl_mode_for_job(job),
                discovery_input=_discovery_input_for_response(job),
                updated_at=job.updated_at.isoformat(),
                total_records=progress.total_records,
                clean_records=clean_count,
                clean_candidates=quality_summary.clean_candidates,
                approved_count=quality_summary.approved_count,
                rejected_count=quality_summary.rejected_count,
                needs_review_count=quality_summary.needs_review_count,
                quality_score=quality_summary.quality_score,
                progress=progress,
                quality_summary=quality_summary,
            )
        )

    return CrawlJobListResponse(items=items)


def _run_job_background(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
        if job is None:
            logger.error("Background run: job %s not found", job_id)
            return
        run_crawl_job_direct(db, job=job)
    except Exception as exc:
        logger.exception("Background run failed for job %s: %s", job_id, exc)
        try:
            db.rollback()
            job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
            if job is not None:
                job.status = "FAILED"
                db.add(job)
                db.commit()
        except Exception:
            logger.exception("Could not mark background job %s as failed", job_id)
    finally:
        db.close()


@router.post("", response_model=CrawlJobCreateResponse, status_code=status.HTTP_201_CREATED)
def create_crawl_job(
    payload: CrawlJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CrawlJobCreateResponse:
    template = _job_template(db, payload.clean_template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Clean template not found")
    _validate_focus_fields_against_template(payload.critical_fields, template)

    sources = _trusted_sources_for_payload(db, payload)
    _validate_trusted_sources(payload, sources)
    resolved_discovery_input = _resolved_discovery_input(payload)

    job = CrawlJob(
        country=payload.country,
        status="QUEUED",
        source_ids=_source_ids_for_job(payload, resolved_discovery_input),
        crawl_mode=payload.crawl_mode,
        discovery_input=resolved_discovery_input,
        critical_fields=payload.critical_fields,
        clean_template_id=payload.clean_template_id,
        ai_assist=payload.ai_assist,
        progress=_default_progress(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_job_background, str(job.id))
    return _create_response_from_progress(job)


@router.get("/{job_id}", response_model=CrawlJobDetailResponse)
def get_crawl_job(job_id: str, db: Session = Depends(get_db)) -> CrawlJobDetailResponse:
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    progress = _progress_for_response(job)
    template = _job_template(db, job.clean_template_id)
    clean_count, quality_summary = _clean_counts_for_response(db, job_id)
    return CrawlJobDetailResponse(
        job_id=str(job.id),
        country=job.country,
        status=job.status,
        source_names=_source_names_for_job(db, job),
        template_name=template.template_name if template is not None else None,
        template_columns=_template_column_names(template),
        crawl_mode=_crawl_mode_for_job(job),
        discovery_input=_discovery_input_for_response(job),
        updated_at=job.updated_at.isoformat(),
        progress=progress,
        clean_records=clean_count,
        clean_candidates=quality_summary.clean_candidates,
        approved_count=quality_summary.approved_count,
        rejected_count=quality_summary.rejected_count,
        needs_review_count=quality_summary.needs_review_count,
        quality_score=quality_summary.quality_score,
        quality_summary=quality_summary,
        critical_fields=_critical_fields_for_job(job),
    )


@router.post("/{job_id}/run", response_model=CrawlJobRunResponse)
def run_crawl_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CrawlJobRunResponse:
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    if job.status in PROCESSING_STATUSES and not _is_stale_processing_job(job):
        return _run_response_from_progress(job, message="Job is already being processed.")
    if _is_stale_processing_job(job):
        logger.warning("Restarting stale crawl job %s from status %s", job_id, job.status)

    job.status = "CRAWLING"
    job.progress = _default_progress()
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_job_background, str(job.id))
    return _run_response_from_progress(job, message="Pipeline started. Poll the job detail endpoint for progress.")


@router.delete("/{job_id}", response_model=CrawlJobDeleteResponse)
def delete_crawl_job(job_id: str, db: Session = Depends(get_db)) -> CrawlJobDeleteResponse:
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    if job.status in PROCESSING_STATUSES and not _is_stale_processing_job(job):
        raise HTTPException(status_code=409, detail="Job is still processing. Wait until it finishes or becomes stale before deleting it.")

    raw_records = db.query(RawRecord).filter(RawRecord.job_id == job_id).all()
    clean_records = db.query(CleanRecord).filter(CleanRecord.job_id == job_id).all()
    raw_record_ids = [str(record.id) for record in raw_records]
    clean_record_ids = [str(record.id) for record in clean_records]

    ai_logs = (
        db.query(AIExtractionLog).filter(AIExtractionLog.raw_record_id.in_(raw_record_ids)).all()
        if raw_record_ids
        else []
    )
    review_actions = (
        db.query(ReviewAction).filter(ReviewAction.clean_record_id.in_(clean_record_ids)).all()
        if clean_record_ids
        else []
    )

    for item in [*review_actions, *ai_logs, *clean_records, *raw_records, job]:
        db.delete(item)
    db.commit()

    return CrawlJobDeleteResponse(
        job_id=job_id,
        status="DELETED",
        message="Crawl job and related review data were deleted.",
        deleted_raw_records=len(raw_records),
        deleted_ai_logs=len(ai_logs),
        deleted_clean_records=len(clean_records),
        deleted_review_actions=len(review_actions),
    )


class FocusFieldsUpdate(BaseModel):
    focus_fields: list[str] = Field(min_length=1, max_length=30)


class FocusFieldsResponse(BaseModel):
    job_id: str
    focus_fields: list[str]


@router.patch("/{job_id}/focus-fields", response_model=FocusFieldsResponse)
def update_focus_fields(
    job_id: str,
    payload: FocusFieldsUpdate,
    db: Session = Depends(get_db),
) -> FocusFieldsResponse:
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    template = _job_template(db, job.clean_template_id)
    _validate_focus_fields_against_template(payload.focus_fields, template)

    job.critical_fields = payload.focus_fields
    db.add(job)
    db.commit()
    db.refresh(job)

    return FocusFieldsResponse(job_id=str(job.id), focus_fields=job.critical_fields)
