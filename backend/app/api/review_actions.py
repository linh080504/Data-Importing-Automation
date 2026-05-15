from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ai_extraction_log import AIExtractionLog
from app.models.clean_record import CleanRecord
from app.models.review_action import ReviewAction
from app.schemas.review_action import ReviewActionRequest, ReviewActionResponse
from app.services.review_apply import apply_review_action

router = APIRouter(tags=["review-actions"])


@router.post("/review-actions", response_model=ReviewActionResponse)
def submit_review_action(
    payload: ReviewActionRequest,
    db: Session = Depends(get_db),
) -> ReviewActionResponse:
    log = db.query(AIExtractionLog).filter(AIExtractionLog.id == payload.record_id).one_or_none()
    if log is None:
        raise HTTPException(status_code=404, detail="Review record not found")

    extractor_payload = log.ai_1_payload or {}
    extracted_fields = extractor_payload.get("critical_fields", {})
    extracted_field = extracted_fields.get(payload.field_name, {})
    old_value = extracted_field.get("value")

    clean_record = db.query(CleanRecord).filter(CleanRecord.raw_record_id == log.raw_record_id).one_or_none()
    clean_record = apply_review_action(
        clean_record,
        field_name=payload.field_name,
        action=payload.action,
        extracted_value=old_value,
        new_value=payload.new_value,
    )
    if clean_record is not None:
        db.add(clean_record)

    review_action = ReviewAction(
        clean_record_id=str(clean_record.id) if clean_record is not None else None,
        reviewer_id=None,
        old_value=None if old_value is None else str(old_value),
        new_value=None if payload.new_value is None else str(payload.new_value),
        action=payload.action,
        note=payload.note,
    )
    db.add(review_action)
    db.commit()
    db.refresh(review_action)

    return ReviewActionResponse(
        status="SUCCESS",
        message="Review saved and record updated to clean_records",
        review_action_id=str(review_action.id),
    )