from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.clean_record import CleanRecord
from app.models.clean_template import CleanTemplate
from app.models.crawl_job import CrawlJob
from app.schemas.import_readiness import (
    ImportReadinessBlocker,
    ImportReadinessCheck,
    ImportReadinessResponse,
)
from app.services.import_readiness import evaluate_import_readiness

router = APIRouter(tags=["import-readiness"])


@router.get("/crawl-jobs/{job_id}/import-readiness", response_model=ImportReadinessResponse)
def get_import_readiness(job_id: str, db: Session = Depends(get_db)) -> ImportReadinessResponse:
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    template = db.query(CleanTemplate).filter(CleanTemplate.id == job.clean_template_id).one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Clean template not found")

    clean_records = db.query(CleanRecord).filter(CleanRecord.job_id == job_id).all()

    missing_required = 0
    duplicate_count = 0
    schema_mismatch_count = 0
    seen_keys: set[str] = set()

    for clean_record in clean_records:
        unique_key = clean_record.unique_key
        is_duplicate = unique_key in seen_keys
        seen_keys.add(unique_key)

        result = evaluate_import_readiness(
            clean_payload=clean_record.clean_payload or {},
            required_fields=job.critical_fields,
            template_columns=template.columns,
            is_duplicate=is_duplicate,
        )

        for check in result.checks:
            if check.key == "required_critical_fields":
                missing_required += check.blocker_count
            elif check.key == "duplicates":
                duplicate_count += check.blocker_count
            elif check.key == "schema_match":
                schema_mismatch_count += check.blocker_count

    checks = [
        ImportReadinessCheck(
            key="required_critical_fields",
            label="Required critical fields filled",
            passed=missing_required == 0,
            blocker_count=missing_required,
        ),
        ImportReadinessCheck(
            key="duplicates",
            label="No duplicate records detected",
            passed=duplicate_count == 0,
            blocker_count=duplicate_count,
        ),
        ImportReadinessCheck(
            key="schema_match",
            label="Schema matches template",
            passed=schema_mismatch_count == 0,
            blocker_count=schema_mismatch_count,
        ),
    ]

    blockers = [
        ImportReadinessBlocker(key=check.key, label=check.label, count=check.blocker_count)
        for check in checks
        if not check.passed and check.blocker_count > 0
    ]

    return ImportReadinessResponse(
        is_ready=all(check.passed for check in checks),
        checks=checks,
        blockers=blockers,
    )
