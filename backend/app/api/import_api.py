from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.clean_record import CleanRecord
from app.models.clean_template import CleanTemplate
from app.models.crawl_job import CrawlJob
from app.models.import_log import ImportLog
from app.schemas.import_api import ImportResponse
from app.services.import_readiness import evaluate_import_readiness
from app.services.importer import upsert_import_records

router = APIRouter(tags=["import"])


@router.post("/crawl-jobs/{job_id}/import", response_model=ImportResponse)
def import_crawl_job(job_id: str, db: Session = Depends(get_db)) -> ImportResponse:
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

    if missing_required > 0 or duplicate_count > 0 or schema_mismatch_count > 0:
        raise HTTPException(status_code=400, detail="Import readiness blockers must be resolved before importing")

    existing_records = [
        {"unique_key": clean_record.unique_key, **(clean_record.clean_payload or {})}
        for clean_record in clean_records
    ]
    result = upsert_import_records(
        existing_records=[],
        incoming_records=existing_records,
    )

    error_summary = {
        "duplicates": result.duplicates,
        "total_records": len(clean_records),
    }
    import_log = ImportLog(
        target_system="BeyondDegree",
        total_records=len(clean_records),
        imported_records=result.inserted + result.updated,
        failed_records=result.duplicates,
        error_summary=error_summary,
    )
    db.add(import_log)
    db.commit()
    db.refresh(import_log)

    return ImportResponse(
        job_id=str(job.id),
        status="COMPLETED",
        message="Import completed successfully",
        inserted_records=result.inserted,
        updated_records=result.updated,
        duplicate_records=result.duplicates,
        total_records=len(clean_records),
        imported_records=result.inserted + result.updated,
    )
