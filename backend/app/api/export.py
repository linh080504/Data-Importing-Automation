from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.clean_record import CleanRecord
from app.models.clean_template import CleanTemplate
from app.models.crawl_job import CrawlJob
from app.schemas.export import ExportRequest, ExportResponse
from app.services.exporter import export_clean_records_to_csv, export_clean_records_to_xlsx
from app.services.template_defaults import defaults_for_job

router = APIRouter(tags=["export"])


def _export_csv_evidence_safe(
    clean_records: list[object],
    *,
    template_columns: list[dict],
    defaults: dict[str, object],
) -> bytes:
    try:
        return export_clean_records_to_csv(
            clean_records,
            template_columns=template_columns,
            defaults=defaults,
            allow_rule_based_defaults=True,
        )
    except TypeError:
        return export_clean_records_to_csv(clean_records, template_columns=template_columns)


def _export_xlsx_evidence_safe(
    clean_records: list[object],
    *,
    template_columns: list[dict],
    defaults: dict[str, object],
) -> bytes:
    try:
        return export_clean_records_to_xlsx(
            clean_records,
            template_columns=template_columns,
            defaults=defaults,
            allow_rule_based_defaults=True,
        )
    except TypeError:
        return export_clean_records_to_xlsx(clean_records, template_columns=template_columns)


@router.post("/crawl-jobs/{job_id}/export", response_model=ExportResponse)
def export_crawl_job(job_id: str, payload: ExportRequest, db: Session = Depends(get_db)) -> ExportResponse:
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    template = db.query(CleanTemplate).filter(CleanTemplate.id == job.clean_template_id).one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Clean template not found")

    clean_records = db.query(CleanRecord).filter(CleanRecord.job_id == job_id).all()
    defaults = defaults_for_job(job)

    if payload.format == "xlsx":
        _export_xlsx_evidence_safe(clean_records, template_columns=template.columns, defaults=defaults)
        download_url = f"/exports/{job_id}_clean.xlsx"
    else:
        _export_csv_evidence_safe(clean_records, template_columns=template.columns, defaults=defaults)
        download_url = f"/exports/{job_id}_clean.csv"

    return ExportResponse(
        download_url=download_url,
        schema_used=template.template_name,
        total_exported=len(clean_records),
    )


@router.get("/crawl-jobs/{job_id}/download")
def download_export(job_id: str, format: str = "csv", db: Session = Depends(get_db)):
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    template = db.query(CleanTemplate).filter(CleanTemplate.id == job.clean_template_id).one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Clean template not found")

    clean_records = db.query(CleanRecord).filter(CleanRecord.job_id == job_id).all()
    defaults = defaults_for_job(job)

    if format == "xlsx":
        content = _export_xlsx_evidence_safe(clean_records, template_columns=template.columns, defaults=defaults)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = _export_csv_evidence_safe(clean_records, template_columns=template.columns, defaults=defaults)
        media_type = "text/csv"

    file_name = f"{job_id}_clean.{format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
    )
