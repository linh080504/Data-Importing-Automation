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


def _has_evidence(extracted_field: dict) -> bool:
    for key in ("source_excerpt", "evidence_url", "evidence_source"):
        value = extracted_field.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _clean_value_for_field(extracted_field: dict, validation: dict) -> object | None:
    value = extracted_field.get("value")
    corrected_value = validation.get("corrected_value") if isinstance(validation, dict) else None

    if corrected_value is not None:
        return corrected_value

    if isinstance(validation, dict) and validation.get("is_correct") is False:
        return None

    if extracted_field.get("evidence_required") and value is not None and not _has_evidence(extracted_field):
        return None

    return value


def _raw_field_value(raw_payload: dict, field_name: str) -> object | None:
    merge_payload = raw_payload.get("_merge") if isinstance(raw_payload.get("_merge"), dict) else {}
    field_sources = merge_payload.get("field_sources") if isinstance(merge_payload, dict) else {}
    source_payloads = raw_payload.get("sources") if isinstance(raw_payload.get("sources"), dict) else {}
    source_id = field_sources.get(field_name) if isinstance(field_sources, dict) else None
    source_payload = source_payloads.get(source_id) if source_id is not None and isinstance(source_payloads, dict) else None
    if isinstance(source_payload, dict) and field_name in source_payload:
        return source_payload.get(field_name)
    return raw_payload.get(field_name)


def _raw_pass_through_payload(raw_payload: dict | None) -> dict:
    if not isinstance(raw_payload, dict):
        return {}

    payload: dict[str, object] = {}
    for field_name, value in raw_payload.items():
        if field_name in {"sources", "_merge"} or field_name.startswith("_"):
            continue
        if value in (None, "", [], {}):
            continue
        payload[field_name] = _raw_field_value(raw_payload, field_name)
    return payload


def build_clean_payload(log: AIExtractionLog | object, *, raw_payload: dict | None = None) -> dict:
    extractor_payload = getattr(log, "ai_1_payload", {}) or {}
    judge_payload = getattr(log, "ai_2_validation", {}) or {}

    extracted_fields = extractor_payload.get("critical_fields", {}) or {}
    fields_validation = (judge_payload.get("judge_output", {}) or {}).get("fields_validation", {}) or {}

    clean_payload: dict[str, object] = {}
    for field_name, extracted_field in extracted_fields.items():
        if not isinstance(extracted_field, dict):
            clean_payload[field_name] = None
            continue
        validation = fields_validation.get(field_name, {}) or {}
        clean_payload[field_name] = _clean_value_for_field(
            extracted_field,
            validation if isinstance(validation, dict) else {},
        )

    for field_name, value in _raw_pass_through_payload(raw_payload).items():
        clean_payload.setdefault(field_name, value)

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
    clean_record.clean_payload = build_clean_payload(ai_log, raw_payload=getattr(raw_record, "raw_payload", None))
    clean_record.quality_score = getattr(ai_log, "overall_confidence", None)
    clean_record.status = derive_clean_record_status(ai_log)

    db.add(clean_record)
    db.commit()
    db.refresh(clean_record)
    return CleanDataResult(clean_record=clean_record, created=created)
