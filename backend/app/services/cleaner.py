from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.ai_extraction_log import AIExtractionLog
from app.models.clean_record import CleanRecord
from app.models.raw_record import RawRecord


@dataclass
class CleanDataResult:
    clean_record: CleanRecord
    created: bool


def build_clean_payload(log: AIExtractionLog | object) -> dict:
    extractor_payload = getattr(log, "ai_1_payload", {}) or {}
    judge_payload = getattr(log, "ai_2_validation", {}) or {}

    extracted_fields = extractor_payload.get("critical_fields", {}) or {}
    fields_validation = (judge_payload.get("judge_output", {}) or {}).get("fields_validation", {}) or {}

    clean_payload: dict[str, object] = {}
    for field_name, extracted_field in extracted_fields.items():
        value = extracted_field.get("value") if isinstance(extracted_field, dict) else None
        validation = fields_validation.get(field_name, {}) or {}
        corrected_value = validation.get("corrected_value") if isinstance(validation, dict) else None
        clean_payload[field_name] = corrected_value if corrected_value is not None else value

    return clean_payload


def derive_clean_record_status(log: AIExtractionLog | object) -> str:
    judge_payload = getattr(log, "ai_2_validation", {}) or {}
    scoring = judge_payload.get("scoring", {}) or {}
    decision = scoring.get("decision")

    if decision == "AUTO_APPROVE":
        return "APPROVED"
    if decision == "REJECT":
        return "REJECTED"
    return "NEEDS_REVIEW"



def generate_clean_record(
    db: Session,
    *,
    raw_record: RawRecord | object,
    ai_log: AIExtractionLog | object,
) -> CleanDataResult:
    existing = (
        db.query(CleanRecord)
        .filter(CleanRecord.job_id == raw_record.job_id, CleanRecord.unique_key == raw_record.unique_key)
        .one_or_none()
    )
    created = existing is None

    clean_record = existing or CleanRecord(
        job_id=raw_record.job_id,
        raw_record_id=raw_record.id,
        unique_key=raw_record.unique_key,
        clean_payload={},
    )

    clean_record.job_id = raw_record.job_id
    clean_record.raw_record_id = raw_record.id
    clean_record.unique_key = raw_record.unique_key
    clean_record.clean_payload = build_clean_payload(ai_log)
    clean_record.quality_score = getattr(ai_log, "overall_confidence", None)
    clean_record.status = derive_clean_record_status(ai_log)

    db.add(clean_record)
    db.commit()
    db.refresh(clean_record)
    return CleanDataResult(clean_record=clean_record, created=created)
