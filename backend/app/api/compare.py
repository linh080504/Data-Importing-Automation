import json
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.clean_record import CleanRecord
from app.models.clean_template import CleanTemplate
from app.models.crawl_job import CrawlJob
from app.models.raw_record import RawRecord
from app.schemas.compare import CompareField, CompareRecord, CompareResponse
from app.services.export_mapping import map_clean_payload_to_template
from app.services.template_defaults import defaults_for_job

router = APIRouter(tags=["compare"])

SCHOOL_ENTITY_TERMS = (
    "university",
    "college",
    "institute",
    "academy",
    "school",
    "conservatory",
    "polytechnic",
)


def _display_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        scalar_items = [item for item in value if item is not None]
        if len(scalar_items) == 1 and isinstance(scalar_items[0], (str, int, float, bool)):
            return scalar_items[0]
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _is_country_list_artifact(raw_payload: dict[str, Any]) -> bool:
    source_url = str(raw_payload.get("source_url") or raw_payload.get("reference_url") or raw_payload.get("source_href") or "")
    page_ref = unquote(source_url.rsplit("/wiki/", 1)[-1]).replace("_", " ").lower()
    if not page_ref.startswith(("list of universities", "lists of universities", "list of colleges", "lists of colleges")):
        return False
    name = str(raw_payload.get("name") or raw_payload.get("title") or raw_payload.get("institution_name") or "")
    return not any(term in name.lower() for term in SCHOOL_ENTITY_TERMS)


def _template_field_order(template_columns: list[dict[str, Any]]) -> list[str]:
    ordered = sorted(
        template_columns,
        key=lambda column: column.get("order") if isinstance(column.get("order"), int) else 0,
    )
    return [str(column.get("name") or "").strip() for column in ordered if str(column.get("name") or "").strip()]


def _compare_field_order(
    *,
    raw_payload: dict[str, Any],
    clean_payload: dict[str, object | None],
    template_fields: list[str],
) -> list[str]:
    excluded = {"sources", "_merge"}
    fields: list[str] = []
    seen: set[str] = set()
    for field_name in [*template_fields, *sorted(set(raw_payload) | set(clean_payload))]:
        if field_name in excluded or field_name in seen:
            continue
        seen.add(field_name)
        fields.append(field_name)
    return fields


@router.get("/crawl-jobs/{job_id}/compare", response_model=CompareResponse)
def get_compare(job_id: str, db: Session = Depends(get_db)) -> CompareResponse:
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
    if job is None:
        return CompareResponse(total=0, items=[])

    template_id = getattr(job, "clean_template_id", None)
    template = db.query(CleanTemplate).filter(CleanTemplate.id == template_id).one_or_none() if template_id else None
    template_columns = template.columns if template is not None else []
    template_fields = _template_field_order(template_columns)
    defaults = defaults_for_job(job)

    raw_records = db.query(RawRecord).filter(RawRecord.job_id == job_id).all()
    clean_records = db.query(CleanRecord).filter(CleanRecord.job_id == job_id).all()
    clean_by_key = {record.unique_key: record for record in clean_records}

    items: list[CompareRecord] = []
    for raw_record in raw_records:
        clean_record = clean_by_key.get(raw_record.unique_key)
        if clean_record is None:
            continue

        raw_payload = raw_record.raw_payload or {}
        if isinstance(raw_payload, dict) and _is_country_list_artifact(raw_payload):
            continue
        clean_payload = clean_record.clean_payload or {}
        if template_columns:
            clean_payload = map_clean_payload_to_template(
                clean_payload,
                template_columns=template_columns,
                defaults=defaults,
                allow_rule_based_defaults=True,
            )
        field_names = _compare_field_order(
            raw_payload=raw_payload,
            clean_payload=clean_payload,
            template_fields=template_fields,
        )
        merge_payload = (raw_payload.get("_merge") or {}) if isinstance(raw_payload, dict) else {}
        field_sources = merge_payload.get("field_sources") or {}
        source_names = merge_payload.get("source_names") or {}
        source_order = merge_payload.get("source_order") or []
        conflicts = merge_payload.get("conflicts") or {}
        primary_source_id = source_order[0] if source_order else None
        fields = [
            CompareField(
                field_name=field_name,
                raw_value=_display_value(raw_payload.get(field_name)),
                clean_value=_display_value(clean_payload.get(field_name)),
                merge_source_id=field_sources.get(field_name),
                merge_source_name=source_names.get(field_sources.get(field_name), field_sources.get(field_name)),
                merge_from_secondary=field_sources.get(field_name) is not None and field_sources.get(field_name) != primary_source_id,
                merge_conflicts=list(conflicts.get(field_name) or []),
            )
            for field_name in field_names
        ]

        items.append(
            CompareRecord(
                raw_record_id=str(raw_record.id),
                unique_key=raw_record.unique_key,
                status=clean_record.status,
                quality_score=clean_record.quality_score,
                fields=fields,
            )
        )

    return CompareResponse(total=len(items), items=items)
