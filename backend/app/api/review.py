import json
import re
from html import unescape
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ai_extraction_log import AIExtractionLog
from app.models.crawl_job import CrawlJob
from app.models.raw_record import RawRecord
from app.schemas.review import CrawledFieldSnapshot, FieldToReview, ReviewQueueItem, ReviewQueueResponse

router = APIRouter(tags=["review"])

ReviewValue = str | int | float | bool | None

TECHNICAL_FIELD_NAMES = {
    "_merge",
    "canonical_key",
    "id",
    "record_hash",
    "reference_url",
    "source",
    "source_href",
    "source_id",
    "source_name",
    "source_url",
    "sources",
    "unique_key",
    "url",
    "uuid",
}

DISPLAY_FIELD_PRIORITY = {
    field_name: index
    for index, field_name in enumerate(
        [
            "name",
            "title",
            "institution_name",
            "description",
            "website",
            "country",
            "city",
            "region",
            "address",
            "financials",
            "tuition",
            "rank",
            "rank_display",
            "qs_rank",
            "qs_score",
            "admissions_page_link",
            "email",
            "phone",
        ]
    )
}

SCHOOL_ENTITY_TERMS = (
    "university",
    "college",
    "institute",
    "academy",
    "school",
    "conservatory",
    "polytechnic",
)


def _raw_records_for_job(db: Session, job_id: str) -> list[RawRecord]:
    try:
        return db.query(RawRecord).filter(RawRecord.job_id == job_id).all()
    except Exception:
        raw_records = getattr(db, "raw_records", [])
        if isinstance(raw_records, list):
            return [record for record in raw_records if str(getattr(record, "job_id", "")) == str(job_id)]
        return []


def _logs_for_raw_record_ids(db: Session, raw_record_ids: list[str]) -> list[AIExtractionLog]:
    try:
        query = (
            db.query(AIExtractionLog)
            .filter(AIExtractionLog.raw_record_id.in_(raw_record_ids))
            .order_by(AIExtractionLog.processed_at.desc())
        )
        return query.all()
    except Exception:
        raw_id_set = {str(raw_record_id) for raw_record_id in raw_record_ids}
        logs = getattr(db, "logs", [])
        if not isinstance(logs, list):
            return []
        filtered = [log for log in logs if str(getattr(log, "raw_record_id", "")) in raw_id_set]
        filtered.sort(key=lambda log: getattr(log, "processed_at", 0), reverse=True)
        return filtered


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
                source_excerpt=extracted.get("source_excerpt"),
                evidence_url=extracted.get("evidence_url"),
                evidence_source=extracted.get("evidence_source"),
                evidence_required=bool(extracted.get("evidence_required", False)),
                merge_source_id=validation.get("merge_source_id"),
                merge_source_name=validation.get("merge_source_name"),
                merge_from_secondary=bool(validation.get("merge_from_secondary", False)),
                merge_conflicts=list(validation.get("merge_conflicts") or []),
            )
        )

    return items


def _clean_display_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if "<" in text and ">" in text:
        text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = " ".join(text.split())
    return text or None


def _first_non_blank(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str):
            text = _clean_display_text(value)
            if text:
                return text
        if value not in (None, "", [], {}) and not isinstance(value, (dict, list)):
            return str(value)
    return None


def _review_value(value: Any) -> ReviewValue:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, str):
        return _clean_display_text(value)
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, default=str)
    else:
        rendered = str(value)
    if len(rendered) > 1000:
        rendered = f"{rendered[:997]}..."
    return _clean_display_text(rendered)


def _is_blank(value: object) -> bool:
    return _review_value(value) is None


def _source_payloads(raw_payload: dict) -> list[dict]:
    payloads = [raw_payload]
    sources = raw_payload.get("sources")
    if isinstance(sources, dict):
        payloads.extend(source for source in sources.values() if isinstance(source, dict))
    return payloads


def _source_url_from_payload(payload: dict[str, Any]) -> str | None:
    return _first_non_blank(payload.get("source_url"), payload.get("reference_url"), payload.get("source_href"), payload.get("url"))


def _is_country_list_artifact(raw_record: RawRecord | object | None) -> bool:
    raw_payload = getattr(raw_record, "raw_payload", None) if raw_record is not None else None
    if not isinstance(raw_payload, dict):
        return False
    source_url = _source_url_from_payload(raw_payload) or ""
    page_ref = unquote(source_url.rsplit("/wiki/", 1)[-1]).replace("_", " ").lower()
    if not page_ref.startswith(("list of universities", "lists of universities", "list of colleges", "lists of colleges")):
        return False
    name = _first_non_blank(raw_payload.get("name"), raw_payload.get("title"), raw_payload.get("institution_name")) or ""
    return not any(term in name.lower() for term in SCHOOL_ENTITY_TERMS)


def _source_name_from_payload(payload: dict[str, Any]) -> str | None:
    return _first_non_blank(payload.get("source_name"), payload.get("source"))


def _display_name_for_review(log: AIExtractionLog, raw_record: RawRecord | object | None) -> str:
    ai1 = getattr(log, "ai_1_payload", None) or {}
    extracted_fields = ai1.get("critical_fields", {}) if isinstance(ai1, dict) else {}
    extracted_name = extracted_fields.get("name", {}) if isinstance(extracted_fields, dict) else {}
    if isinstance(extracted_name, dict):
        name = _first_non_blank(extracted_name.get("value"))
        if name:
            return name

    raw_payload = getattr(raw_record, "raw_payload", None) if raw_record is not None else None
    if isinstance(raw_payload, dict):
        for payload in _source_payloads(raw_payload):
            name = _first_non_blank(
                payload.get("name"),
                payload.get("title"),
                payload.get("institution_name"),
                payload.get("teN_DON_VI"),
                payload.get("teN_TIENG_ANH"),
            )
            if name:
                return name

    unique_key = _first_non_blank(getattr(raw_record, "unique_key", None))
    if unique_key:
        return unique_key
    return str(getattr(log, "raw_record_id", "Unknown record"))


def _source_url_for_review(raw_record: RawRecord | object | None) -> str | None:
    raw_payload = getattr(raw_record, "raw_payload", None) if raw_record is not None else None
    if not isinstance(raw_payload, dict):
        return None
    for payload in _source_payloads(raw_payload):
        url = _source_url_from_payload(payload)
        if url:
            return url
    return None


def _source_name_for_review(raw_record: RawRecord | object | None) -> str | None:
    raw_payload = getattr(raw_record, "raw_payload", None) if raw_record is not None else None
    if not isinstance(raw_payload, dict):
        return None
    merge = raw_payload.get("_merge")
    source_names = merge.get("source_names") if isinstance(merge, dict) else None
    field_sources = merge.get("field_sources") if isinstance(merge, dict) else None
    if isinstance(source_names, dict) and isinstance(field_sources, dict):
        for field_name in ("name", "website", "source_url", "reference_url"):
            source_id = field_sources.get(field_name)
            name = _first_non_blank(source_names.get(source_id)) if source_id is not None else None
            if name:
                return name
    if isinstance(source_names, dict):
        name = _first_non_blank(*source_names.values())
        if name:
            return name
    return _source_name_from_payload(raw_payload)


def _unique_key_for_review(log: AIExtractionLog, raw_record: RawRecord | object | None) -> str:
    return (
        _first_non_blank(
            getattr(raw_record, "unique_key", None) if raw_record is not None else None,
            getattr(log, "raw_record_id", None),
            getattr(log, "id", None),
        )
        or "unknown-record"
    )


def _source_context_for_field(
    raw_payload: dict[str, Any],
    field_name: str,
    extracted: dict[str, Any],
) -> tuple[str | None, str | None]:
    merge = raw_payload.get("_merge") if isinstance(raw_payload.get("_merge"), dict) else {}
    field_sources = merge.get("field_sources") if isinstance(merge, dict) else {}
    source_names = merge.get("source_names") if isinstance(merge, dict) else {}
    sources = raw_payload.get("sources") if isinstance(raw_payload.get("sources"), dict) else {}

    source_id = field_sources.get(field_name) if isinstance(field_sources, dict) else None
    source_payload = sources.get(source_id) if source_id is not None and isinstance(sources, dict) else None
    if not isinstance(source_payload, dict):
        source_payload = raw_payload
    fallback_source_name = _first_non_blank(*source_names.values()) if isinstance(source_names, dict) else None

    evidence_url = _first_non_blank(extracted.get("evidence_url"), _source_url_from_payload(source_payload), _source_url_from_payload(raw_payload))
    evidence_source = _first_non_blank(
        extracted.get("evidence_source"),
        source_names.get(source_id) if source_id is not None and isinstance(source_names, dict) else None,
        _source_name_from_payload(source_payload),
        _source_name_from_payload(raw_payload),
        fallback_source_name,
    )
    return evidence_url, evidence_source


def _raw_value_for_field(raw_payload: dict[str, Any], field_name: str) -> Any:
    merge = raw_payload.get("_merge") if isinstance(raw_payload.get("_merge"), dict) else {}
    field_sources = merge.get("field_sources") if isinstance(merge, dict) else {}
    sources = raw_payload.get("sources") if isinstance(raw_payload.get("sources"), dict) else {}
    source_id = field_sources.get(field_name) if isinstance(field_sources, dict) else None
    source_payload = sources.get(source_id) if source_id is not None and isinstance(sources, dict) else None
    if isinstance(source_payload, dict) and field_name in source_payload:
        return source_payload.get(field_name)
    if field_name in raw_payload:
        return raw_payload.get(field_name)
    if isinstance(sources, dict):
        for payload in sources.values():
            if isinstance(payload, dict) and field_name in payload:
                return payload.get(field_name)
    return None


def _field_sort_key(snapshot: CrawledFieldSnapshot) -> tuple[int, int, str]:
    issue_rank = 0 if snapshot.status in {"needs_review", "missing"} else 1
    return (DISPLAY_FIELD_PRIORITY.get(snapshot.field_name, len(DISPLAY_FIELD_PRIORITY)), issue_rank, snapshot.field_name)


def _build_crawled_field_snapshots(
    log: AIExtractionLog,
    raw_record: RawRecord | object | None,
    fields_to_review: list[FieldToReview],
) -> list[CrawledFieldSnapshot]:
    raw_payload = getattr(raw_record, "raw_payload", None) if raw_record is not None else None
    if not isinstance(raw_payload, dict):
        raw_payload = {}

    ai1 = getattr(log, "ai_1_payload", None) or {}
    extracted_fields = ai1.get("critical_fields", {}) if isinstance(ai1, dict) else {}
    if not isinstance(extracted_fields, dict):
        extracted_fields = {}

    review_by_field = {field.field_name: field for field in fields_to_review}
    field_names: set[str] = set(review_by_field)
    field_names.update(str(field_name) for field_name in extracted_fields if isinstance(field_name, str))
    field_names.update(
        field_name
        for field_name, value in raw_payload.items()
        if isinstance(field_name, str)
        and field_name not in TECHNICAL_FIELD_NAMES
        and not field_name.startswith("_")
        and (not _is_blank(value) or field_name in review_by_field)
    )

    snapshots: list[CrawledFieldSnapshot] = []
    for field_name in field_names:
        extracted = extracted_fields.get(field_name, {})
        if not isinstance(extracted, dict):
            extracted = {}

        extracted_value = _review_value(extracted.get("value"))
        raw_value = _review_value(_raw_value_for_field(raw_payload, field_name))
        value = extracted_value if extracted_value is not None else raw_value
        field_to_review = review_by_field.get(field_name)
        evidence_url, evidence_source = _source_context_for_field(raw_payload, field_name, extracted)

        status = "captured"
        reason: str | None = None
        if field_to_review is not None:
            status = "missing" if value is None else "needs_review"
            reason = field_to_review.reason
        elif value is None:
            status = "missing"
            reason = "No source-backed value was captured."

        source_excerpt = _review_value(extracted.get("source_excerpt"))

        snapshots.append(
            CrawledFieldSnapshot(
                field_name=field_name,
                value=value,
                source_url=evidence_url,
                source_name=evidence_source,
                source_excerpt=str(source_excerpt) if source_excerpt is not None else None,
                status=status,
                reason=reason,
            )
        )

    snapshots.sort(key=_field_sort_key)
    return snapshots


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

    raw_records = _raw_records_for_job(db, job_id)
    raw_record_map = {str(record.id): record for record in raw_records}
    raw_record_ids = list(raw_record_map.keys())
    logs = _logs_for_raw_record_ids(db, raw_record_ids)

    all_items: list[ReviewQueueItem] = []
    for log in logs:
        fields_to_review = _build_fields_to_review(log)
        if not fields_to_review:
            continue
        raw_record = raw_record_map.get(str(log.raw_record_id))
        if _is_country_list_artifact(raw_record):
            continue

        all_items.append(
            ReviewQueueItem(
                record_id=str(log.id),
                raw_record_id=str(log.raw_record_id),
                display_name=_display_name_for_review(log, raw_record),
                unique_key=_unique_key_for_review(log, raw_record),
                source_url=_source_url_for_review(raw_record),
                source_name=_source_name_for_review(raw_record),
                overall_confidence=log.overall_confidence,
                crawled_fields=_build_crawled_field_snapshots(log, raw_record, fields_to_review),
                fields_to_review=fields_to_review,
            )
        )

    total = len(all_items)
    items = all_items[offset : offset + limit]
    return ReviewQueueResponse(total=total, page=page, limit=limit, items=items)
