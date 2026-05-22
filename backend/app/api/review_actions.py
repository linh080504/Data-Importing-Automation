from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ai_extraction_log import AIExtractionLog
from app.models.clean_record import CleanRecord
from app.models.review_action import ReviewAction
from app.schemas.review_action import ReviewActionRequest, ReviewActionResponse
from app.services.review_apply import apply_review_action

router = APIRouter(tags=["review-actions"])


def _final_value_for_action(action: str, *, extracted_value: object, new_value: object | None) -> object | None:
    if action == "ACCEPT":
        return extracted_value
    if action == "EDIT":
        return new_value
    return None


def _mark_field_reviewed(log: AIExtractionLog | object, *, field_name: str, final_value: object | None, action: str) -> None:
    ai_2_validation = dict(getattr(log, "ai_2_validation", None) or {})
    judge_output = dict(ai_2_validation.get("judge_output") or {})
    fields_validation = dict(judge_output.get("fields_validation") or {})
    validation = dict(fields_validation.get(field_name) or {})
    validation.update(
        {
            "is_correct": True,
            "corrected_value": final_value,
            "confidence": 100,
            "reason": f"Human review resolved this field with action {action}.",
        }
    )
    fields_validation[field_name] = validation
    judge_output["fields_validation"] = fields_validation
    unresolved = any(
        not (item.get("is_correct", False) if isinstance(item, dict) else False)
        for item in fields_validation.values()
    )
    judge_output["status"] = "NEEDS_REVIEW" if unresolved else "APPROVED"
    ai_2_validation["judge_output"] = judge_output
    log.ai_2_validation = ai_2_validation
    confidences = [
        item.get("confidence")
        for item in fields_validation.values()
        if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float))
    ]
    if confidences:
        log.overall_confidence = round(sum(confidences) / len(confidences))


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
    final_value = _final_value_for_action(payload.action, extracted_value=old_value, new_value=payload.new_value)

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
    _mark_field_reviewed(log, field_name=payload.field_name, final_value=final_value, action=payload.action)
    db.add(log)

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
        field_name=payload.field_name,
        final_value=final_value if isinstance(final_value, (str, int, float, bool)) or final_value is None else str(final_value),
        record_status=getattr(clean_record, "status", None),
    )
