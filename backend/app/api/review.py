from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ai_extraction_log import AIExtractionLog
from app.models.crawl_job import CrawlJob
from app.models.raw_record import RawRecord
from app.schemas.review import FieldToReview, ReviewQueueItem, ReviewQueueResponse

router = APIRouter(tags=["review"])


def _build_fields_to_review(log: AIExtractionLog) -> list[FieldToReview]:
    ai1 = log.ai_1_payload or {}
    ai2 = (log.ai_2_validation or {}).get("judge_output", {})

    extracted_fields = ai1.get("critical_fields", {})
    field_validations = ai2.get("fields_validation", {})

    items: list[FieldToReview] = []
    for field_name, validation in field_validations.items():
        is_correct = validation.get("is_correct", False)
        confidence = validation.get("confidence", 0)
        if is_correct and confidence >= 85 and not validation.get("merge_conflicts"):
            continue

        extracted = extracted_fields.get(field_name, {})
        items.append(
            FieldToReview(
                field_name=field_name,
                raw_value=extracted.get("value"),
                suggested_value=validation.get("corrected_value", extracted.get("value")),
                confidence=round(confidence / 100, 2),
                reason=validation.get("reason") or "Low confidence or mismatch detected",
                merge_source_id=validation.get("merge_source_id"),
                merge_source_name=validation.get("merge_source_name"),
                merge_from_secondary=bool(validation.get("merge_from_secondary", False)),
                merge_conflicts=list(validation.get("merge_conflicts") or []),
            )
        )

    return items


@router.get("/crawl-jobs/{job_id}/review-queue", response_model=ReviewQueueResponse)
def get_review_queue(
    job_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ReviewQueueResponse:
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
    if job is None:
        return ReviewQueueResponse(total=0, page=page, limit=limit, items=[])

    offset = (page - 1) * limit

    raw_record_ids = [record.id for record in db.query(RawRecord).filter(RawRecord.job_id == job_id).all()]
    query = db.query(AIExtractionLog).filter(AIExtractionLog.raw_record_id.in_(raw_record_ids)).order_by(AIExtractionLog.processed_at.desc())
    logs = query.offset(offset).limit(limit).all()

    items: list[ReviewQueueItem] = []
    for log in logs:
        fields_to_review = _build_fields_to_review(log)
        if not fields_to_review:
            continue

        items.append(
            ReviewQueueItem(
                record_id=str(log.id),
                raw_record_id=str(log.raw_record_id),
                overall_confidence=log.overall_confidence,
                fields_to_review=fields_to_review,
            )
        )

    total = len(items)
    return ReviewQueueResponse(total=total, page=page, limit=limit, items=items)
