from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.crawl_job import CrawlJob
from app.models.clean_record import CleanRecord
from app.models.clean_template import CleanTemplate
from app.models.data_source import DataSource
from app.models.raw_record import RawRecord
from app.schemas.ai_output import AIExtractorOutput
from app.schemas.discovery import DiscoverySourceBundle
from app.services.ai_extractor import ExtractRequest, extract_critical_fields
from app.services.discovery_prompt import PromptDiscoveryRequest, discover_universities_from_prompt, prompt_result_to_bundle
from app.services.discovery_sources import fetch_discovery_bundle_from_source
from app.services.gemini_client import GeminiRateLimitError, build_gemini_client
from app.services.source_adapters.escaped_jsonld import load_escaped_jsonld_item_list
from app.services.ai_judge import JudgeRequest, judge_extraction
from app.services.cleaner import generate_clean_record
from app.services.logging import log_ai_extraction
from app.services.raw_ingest import upsert_raw_record
from app.services.required_fields import required_fields_for_job
from app.services.scoring import calculate_weighted_confidence
from app.services.source_registry import build_trusted_source_discovery_input
from app.services.supplemental_registry import build_supplemental_discovery_input
from app.services.validator import validate_critical_fields

logger = logging.getLogger(__name__)


class DirectRunError(RuntimeError):
    pass


@dataclass
class DirectRunResult:
    total_records: int
    crawled: int
    extracted: int
    needs_review: int
    cleaned: int
    skipped: int = 0
    clean_candidates: int = 0
    approved: int = 0
    rejected: int = 0
    processed: int = 0
    status: str = "QUEUED"


def _build_progress(
    *,
    total_records: int,
    crawled: int,
    extracted: int,
    needs_review: int,
    cleaned: int,
    skipped: int = 0,
    clean_candidates: int = 0,
    approved: int = 0,
    rejected: int = 0,
    processed: int | None = None,
) -> dict[str, int]:
    return {
        "total_records": total_records,
        "crawled": crawled,
        "extracted": extracted,
        "needs_review": needs_review,
        "cleaned": cleaned,
        "skipped": skipped,
        "clean_candidates": clean_candidates,
        "approved": approved,
        "rejected": rejected,
        "processed": extracted if processed is None else processed,
    }


def _is_blank_candidate_value(value: Any) -> bool:
    return value in (None, "", [], {})


def _column_names(template_columns: list[dict[str, Any]] | None) -> list[str]:
    if not template_columns:
        return []
    return [
        str(column.get("name")).strip()
        for column in sorted(template_columns, key=lambda item: item.get("order", 0) if isinstance(item.get("order", 0), int) else 0)
        if column.get("name") and str(column.get("name")).strip()
    ]


def _is_system_or_derived_field(field_name: str) -> bool:
    return field_name in {"id", "slug"}


def _target_fields_for_row(
    prepared_row: "PreparedRow",
    critical_fields: list[str],
    template_columns: list[dict[str, Any]] | None = None,
) -> list[str]:
    template_fields = _column_names(template_columns)
    template_field_set = set(template_fields)
    row_fields = [
        field_name
        for field_name, value in prepared_row.normalized.items()
        if not field_name.startswith("_")
        and not _is_system_or_derived_field(field_name)
        and not _is_blank_candidate_value(value)
        and (not template_field_set or field_name in template_field_set or field_name in critical_fields)
    ]

    ordered_fields: list[str] = []
    for field_name in [*critical_fields, *template_fields, *sorted(row_fields)]:
        if not field_name or field_name in ordered_fields:
            continue
        if _is_system_or_derived_field(field_name):
            continue
        if field_name in critical_fields or field_name in row_fields:
            ordered_fields.append(field_name)
    return ordered_fields


def _evidence_url_for_field(raw_payload: dict[str, Any], field_name: str) -> str | None:
    merge_metadata = raw_payload.get("_merge") or {}
    field_sources = merge_metadata.get("field_sources") or {}
    source_payloads = raw_payload.get("sources") or {}
    source_id = field_sources.get(field_name)
    candidate_payloads: list[dict[str, Any]] = []
    if source_id and isinstance(source_payloads, dict) and isinstance(source_payloads.get(source_id), dict):
        candidate_payloads.append(source_payloads[source_id])
    candidate_payloads.append(raw_payload)

    for payload in candidate_payloads:
        for key in ("source_url", "source_href", "url", "website", "admissions_page_link"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _evidence_excerpt_for_field(*, field_name: str, value: Any, raw_text: str) -> str | None:
    if _is_blank_candidate_value(value):
        return None
    text_value = str(value)
    if text_value and raw_text and text_value in raw_text:
        return text_value
    if raw_text:
        return raw_text[:500]
    return text_value


def _source_name_for_field(raw_payload: dict[str, Any], field_name: str) -> str | None:
    merge_metadata = raw_payload.get("_merge") or {}
    field_sources = merge_metadata.get("field_sources") or {}
    source_names = merge_metadata.get("source_names") or {}
    source_id = field_sources.get(field_name)
    if source_id is None:
        return None
    return source_names.get(source_id, source_id)


def _candidate_value_for_field(prepared_row: "PreparedRow", field_name: str) -> Any:
    value = _field_value_from_row(prepared_row.raw_payload, field_name)
    if _is_blank_candidate_value(value):
        return prepared_row.normalized.get(field_name)
    return value


def _build_clean_candidate_from_row(
    prepared_row: "PreparedRow",
    critical_fields: list[str],
    template_columns: list[dict[str, Any]] | None = None,
) -> AIExtractorOutput:
    target_fields = _target_fields_for_row(prepared_row, critical_fields, template_columns)
    schema_adapter = RuleBasedExtractorClient(prepared_row.normalized, target_fields)

    def field_payload(field: str) -> dict[str, Any]:
        candidate_value = _candidate_value_for_field(prepared_row, field)
        has_value = not _is_blank_candidate_value(candidate_value)
        return {
            "value": schema_adapter._schema_value(candidate_value),
            "confidence": 1.0 if has_value else 0.0,
            "source_excerpt": _evidence_excerpt_for_field(
                field_name=field,
                value=candidate_value,
                raw_text=prepared_row.raw_text,
            ),
            "evidence_url": _evidence_url_for_field(prepared_row.raw_payload, field) if has_value else None,
            "evidence_source": _source_name_for_field(prepared_row.raw_payload, field) if has_value else None,
            "evidence_required": True,
        }

    payload = {
        "critical_fields": {
            field: field_payload(field)
            for field in target_fields
        },
        "extraction_notes": [
            "Pre-judge clean candidate built from evidence-backed source data.",
            "Focus fields are included even when missing; non-focus fields are included only when source data has a value.",
        ],
    }
    return AIExtractorOutput.model_validate(payload)


def _count_clean_status(status: str) -> tuple[int, int, int]:
    if status == "APPROVED":
        return 1, 0, 0
    if status == "REJECTED":
        return 0, 0, 1
    return 0, 1, 0


def _is_source_based_crawl(job: CrawlJob | object) -> bool:
    return getattr(job, "crawl_mode", "trusted_sources") != "prompt_discovery"


def _extractor_output_for_row(
    job: CrawlJob | object,
    prepared_row: "PreparedRow",
    template_columns: list[dict[str, Any]] | None = None,
) -> AIExtractorOutput:
    target_fields = _target_fields_for_row(prepared_row, job.critical_fields, template_columns)
    if _is_source_based_crawl(job):
        return _build_clean_candidate_from_row(prepared_row, job.critical_fields, template_columns)

    if job.ai_assist:
        try:
            gemini_client = build_gemini_client()
            return extract_critical_fields(
                ExtractRequest(raw_text=prepared_row.raw_text, critical_fields=target_fields),
                client=gemini_client,
            )
        except Exception:
            logger.exception("AI extractor failed for row %s. Falling back to rule-based extractor.", prepared_row.unique_key)
    return extract_critical_fields(
        ExtractRequest(raw_text=prepared_row.raw_text, critical_fields=target_fields),
        client=RuleBasedExtractorClient(prepared_row.normalized, target_fields),
    )


def _judge_output_for_row(
    job: CrawlJob | object,
    prepared_row: "PreparedRow",
    extractor_output: AIExtractorOutput,
    rule_validation,
    required_fields: list[str],
):
    request = JudgeRequest(
        raw_text=prepared_row.raw_text,
        extractor_output=extractor_output,
        rule_validation=rule_validation,
    )
    if _should_use_ai_judge(job, extractor_output, rule_validation):
        try:
            gemini_client = build_gemini_client()
            return judge_extraction(request, client=gemini_client)
        except Exception:
            logger.exception("AI judge failed for row %s. Falling back to rule-based judge.", prepared_row.unique_key)
    return judge_extraction(request, client=RuleBasedJudgeClient(extractor_output, required_fields))


def _field_has_evidence(field_payload: object) -> bool:
    if not isinstance(field_payload, dict):
        return False
    for key in ("source_excerpt", "evidence_url", "evidence_source"):
        value = field_payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _should_use_ai_judge(job: CrawlJob | object, extractor_output: AIExtractorOutput, rule_validation) -> bool:
    if not getattr(job, "ai_assist", False):
        return False

    if not _is_source_based_crawl(job):
        return True

    missing_required = any(getattr(issue, "code", "") == "required_missing" for issue in getattr(rule_validation, "issues", []))
    if missing_required:
        return False

    fields = extractor_output.model_dump(mode="json").get("critical_fields", {})
    if not isinstance(fields, dict):
        return False

    for field_payload in fields.values():
        if not isinstance(field_payload, dict):
            continue
        if _is_blank_candidate_value(field_payload.get("value")):
            continue
        if _field_has_evidence(field_payload):
            return True
    return False


def _status_from_progress(*, total_records: int, approved: int, needs_review: int, processed: int, rejected: int = 0) -> str:
    if total_records == 0:
        return "QUEUED"
    if needs_review > 0:
        return "NEEDS_REVIEW"
    if processed >= total_records and rejected > 0:
        return "FAILED" if approved == 0 else "NEEDS_REVIEW"
    if processed > 0 and approved == processed:
        return "READY_TO_EXPORT"
    return "CRAWLING"


class RuleBasedExtractorClient:
    def __init__(self, row: dict[str, Any], critical_fields: list[str]) -> None:
        self.row = row
        self.critical_fields = critical_fields

    def _schema_value(self, value: Any) -> str | int | float | bool | None:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            for item in value:
                if item is None:
                    continue
                if isinstance(item, (str, int, float, bool)):
                    return item
                return json.dumps(item, ensure_ascii=False)
            return None
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def generate_json(self, *, prompt: str) -> str:
        del prompt
        payload = {
            "critical_fields": {
                field: {
                    "value": self._schema_value(self.row.get(field)),
                    "confidence": 1.0 if self.row.get(field) is not None else 0.0,
                    "source_excerpt": None if self.row.get(field) is None else str(self._schema_value(self.row.get(field))),
                    "evidence_url": self.row.get("source_url") if self.row.get(field) is not None and isinstance(self.row.get("source_url"), str) else None,
                    "evidence_source": None,
                    "evidence_required": True,
                }
                for field in self.critical_fields
            },
            "extraction_notes": ["AI assist disabled; values copied directly from source row."],
        }
        return json.dumps(payload, ensure_ascii=False)


class RuleBasedJudgeClient:
    def __init__(self, extractor_output: AIExtractorOutput, required_fields: list[str]) -> None:
        self.extractor_output = extractor_output
        self.required_fields = required_fields

    def generate_json(self, *, prompt: str) -> str:
        del prompt
        extracted = {field: value.value for field, value in self.extractor_output.critical_fields.items()}
        validation = validate_critical_fields(extracted, required_fields=self.required_fields)
        fields_validation = {}
        for field in extracted:
            matching_issue = next((issue for issue in validation.issues if issue.field == field), None)
            fields_validation[field] = {
                "is_correct": matching_issue is None,
                "corrected_value": None,
                "confidence": 96 if matching_issue is None else 60,
                "reason": "Matches source" if matching_issue is None else matching_issue.message,
            }
        payload = {
            "fields_validation": fields_validation,
            "overall_confidence": 96 if validation.is_valid else 60,
            "status": "APPROVED" if validation.is_valid else "NEEDS_REVIEW",
            "summary": "Rule-based validation completed.",
        }
        return json.dumps(payload, ensure_ascii=False)


@dataclass
class PreparedRow:
    normalized: dict[str, Any]
    raw_payload: dict[str, Any]
    raw_text: str
    unique_key: str


@dataclass
class PreparedSource:
    source_type: str
    rows: list[PreparedRow]


@dataclass
class MergedPreparedRow:
    source_id: str
    unique_key: str
    normalized: dict[str, Any]
    raw_payload: dict[str, Any]
    raw_text: str
    merge_metadata: dict[str, Any]
    source_order: list[str]
    source_names: dict[str, str]
    field_sources: dict[str, str]
    conflicts: dict[str, list[dict[str, Any]]]
    source_notes: dict[str, str]
    source_types: dict[str, str]
    source_roles: dict[str, str]
    source_labels: dict[str, str]
    source_countries: dict[str, str]
    source_supported_fields: dict[str, list[Any]]
    source_critical_fields: dict[str, list[Any]]
    source_configs: dict[str, dict[str, Any]]


def _source_role(source: object) -> str:
    config = getattr(source, "config", None) or {}
    return str(config.get("role") or config.get("trust_level") or "primary")


def _is_empty_value(value: Any) -> bool:
    return value in (None, "", [], {})


def _canonical_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("đ", "d")
    text = text.replace("viet nam", "vietnam")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _merge_key_for_row(prepared_row: "PreparedRow") -> str:
    unique_key = str(prepared_row.unique_key or "").strip()
    if unique_key and not unique_key.lower().startswith(("http://", "https://", "row-")) and not re.fullmatch(r"Q\d+", unique_key):
        return f"unique:{unique_key}"
    name_key = _canonical_text(prepared_row.normalized.get("name"))
    if name_key:
        country_key = _canonical_text(prepared_row.normalized.get("country"))
        return f"name:{country_key}:{name_key}"
    return f"unique:{unique_key}"


def _clean_record_for_job_key(db: Session, *, job_id: str, unique_key: str) -> CleanRecord | object | None:
    try:
        return (
            db.query(CleanRecord)
            .filter(CleanRecord.job_id == job_id, CleanRecord.unique_key == unique_key)
            .one_or_none()
        )
    except Exception:
        clean_records = getattr(db, "clean_records", [])
        if isinstance(clean_records, list):
            return next(
                (
                    record
                    for record in clean_records
                    if str(getattr(record, "job_id", "")) == str(job_id)
                    and str(getattr(record, "unique_key", "")) == str(unique_key)
                ),
                None,
            )
        return None


def _clean_record_covers_fields(clean_record: CleanRecord | object, prepared_row: "PreparedRow", target_fields: list[str]) -> bool:
    clean_payload = getattr(clean_record, "clean_payload", None)
    if not isinstance(clean_payload, dict):
        return False
    for field_name in target_fields:
        if field_name not in clean_payload:
            return False
        clean_value = clean_payload.get(field_name)
        raw_value = _field_value_from_row(prepared_row.raw_payload, field_name)
        if _is_empty_value(raw_value):
            raw_value = prepared_row.normalized.get(field_name)
        if _is_empty_value(clean_value) and not _is_empty_value(raw_value):
            return False
    return True


def _source_label(source: object) -> str:
    return str(getattr(source, "source_name", None) or getattr(source, "id", "source"))


def _merge_metadata_payload(
    *,
    source_order: list[str],
    field_sources: dict[str, str],
    conflicts: dict[str, list[dict[str, Any]]],
    source_names: dict[str, str],
) -> dict[str, Any]:
    return {
        "source_order": source_order,
        "field_sources": field_sources,
        "conflicts": conflicts,
        "source_names": source_names,
    }


def _build_conflict_entry(*, source_id: str, source_name: str, value: Any) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_name": source_name,
        "value": value,
    }


def _field_value_from_row(raw_payload: dict[str, Any], field_name: str) -> Any:
    merge_metadata = raw_payload.get("_merge") or {}
    field_sources = merge_metadata.get("field_sources") or {}
    source_id = field_sources.get(field_name)
    source_payloads = raw_payload.get("sources") or {}
    if source_id and isinstance(source_payloads, dict):
        source_payload = source_payloads.get(source_id) or {}
        if isinstance(source_payload, dict) and field_name in source_payload:
            return source_payload.get(field_name)
    return raw_payload.get(field_name)


def _annotate_judge_output(*, judge_output: Any, merge_metadata: dict[str, Any], extracted_values: dict[str, Any]) -> None:
    field_sources = merge_metadata.get("field_sources") or {}
    conflicts = merge_metadata.get("conflicts") or {}
    source_names = merge_metadata.get("source_names") or {}
    fields_validation = getattr(judge_output, "fields_validation", {}) or {}

    for field_name, validation in fields_validation.items():
        if field_name in field_sources:
            chosen_source_id = field_sources[field_name]
            validation.reason = f"{validation.reason} Source: {source_names.get(chosen_source_id, chosen_source_id)}."
        if field_name in conflicts:
            chosen_source_id = field_sources.get(field_name)
            chosen_value = extracted_values.get(field_name)
            conflict_entries = [
                _build_conflict_entry(
                    source_id=chosen_source_id,
                    source_name=source_names.get(chosen_source_id, chosen_source_id),
                    value=chosen_value,
                )
            ] if chosen_source_id is not None else []
            conflict_entries.extend(conflicts[field_name])
            validation.reason = f"{validation.reason} Conflict detected across sources."
            setattr(validation, "_merge_conflicts", conflict_entries)
            setattr(validation, "_merge_source_id", chosen_source_id)
            setattr(validation, "_merge_source_name", source_names.get(chosen_source_id, chosen_source_id) if chosen_source_id is not None else None)
        elif field_name in field_sources:
            chosen_source_id = field_sources[field_name]
            setattr(validation, "_merge_source_id", chosen_source_id)
            setattr(validation, "_merge_source_name", source_names.get(chosen_source_id, chosen_source_id))

        if field_name in field_sources:
            setattr(validation, "_merge_from_secondary", field_sources[field_name] != (merge_metadata.get("source_order") or [None])[0])


def _judge_output_payload(judge_output: Any) -> dict[str, Any]:
    payload = judge_output.model_dump(mode="json")
    fields_validation = payload.get("fields_validation") or {}
    for field_name, field_payload in fields_validation.items():
        validation = getattr(judge_output, "fields_validation", {}).get(field_name)
        if validation is None:
            continue
        merge_source_id = getattr(validation, "_merge_source_id", None)
        merge_source_name = getattr(validation, "_merge_source_name", None)
        merge_from_secondary = getattr(validation, "_merge_from_secondary", None)
        merge_conflicts = getattr(validation, "_merge_conflicts", None)
        if merge_source_id is not None:
            field_payload["merge_source_id"] = merge_source_id
        if merge_source_name is not None:
            field_payload["merge_source_name"] = merge_source_name
        if merge_from_secondary is not None:
            field_payload["merge_from_secondary"] = merge_from_secondary
        if merge_conflicts is not None:
            field_payload["merge_conflicts"] = merge_conflicts
    return payload


def _log_ai_extraction_with_merge(
    db: Session,
    *,
    raw_record_id: str,
    extractor_output: AIExtractorOutput,
    judge_output: Any,
    scoring: Any,
    merge_metadata: dict[str, Any],
):
    ai_log = log_ai_extraction(
        db,
        raw_record_id=raw_record_id,
        extractor_output=extractor_output,
        judge_output=judge_output,
        scoring=scoring,
    )
    ai_log.ai_2_validation = {
        **(ai_log.ai_2_validation or {}),
        "judge_output": _judge_output_payload(judge_output),
        "merge": merge_metadata,
    }
    db.add(ai_log)
    db.commit()
    db.refresh(ai_log)
    return ai_log


def _merge_source_catalog(source: object) -> dict[str, Any]:
    config = getattr(source, "config", None) or {}
    return {
        "label": _source_label(source),
        "type": str(config.get("source_type", "json_api")),
        "role": _source_role(source),
        "country": str(getattr(source, "country", "") or ""),
        "supported_fields": list(getattr(source, "supported_fields", None) or []),
        "critical_fields": list(getattr(source, "critical_fields", None) or []),
        "config": dict(config),
        "note": str(config.get("note") or ""),
    }


def _build_merged_raw_payload(*, normalized: dict[str, Any], source_payloads: dict[str, Any], merge_metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        **normalized,
        "sources": source_payloads,
        "_merge": merge_metadata,
    }


def _primary_source_id(source_order: list[str]) -> str | None:
    return source_order[0] if source_order else None


def _merge_field(
    *,
    field_name: str,
    incoming_value: Any,
    source_id: str,
    source_name: str,
    merged_normalized: dict[str, Any],
    field_sources: dict[str, str],
    conflicts: dict[str, list[dict[str, Any]]],
) -> None:
    if field_name.startswith("_"):
        return

    current_value = merged_normalized.get(field_name)
    if _is_empty_value(current_value):
        merged_normalized[field_name] = incoming_value
        if not _is_empty_value(incoming_value):
            field_sources[field_name] = source_id
        return

    if _is_empty_value(incoming_value):
        return

    if current_value != incoming_value:
        conflicts.setdefault(field_name, []).append(
            _build_conflict_entry(source_id=source_id, source_name=source_name, value=incoming_value)
        )


def _merge_source_names(source_order: list[str], source_catalog: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {source_id: source_catalog[source_id]["label"] for source_id in source_order if source_id in source_catalog}


def _merge_source_metadata_map(source_order: list[str], source_catalog: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
    return {source_id: source_catalog[source_id][key] for source_id in source_order if source_id in source_catalog}


def _merged_raw_source_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    sources = raw_payload.get("sources")
    return sources if isinstance(sources, dict) else {}


def _merge_annotation_for_field(raw_payload: dict[str, Any], field_name: str) -> dict[str, Any]:
    merge_metadata = raw_payload.get("_merge") or {}
    field_sources = merge_metadata.get("field_sources") or {}
    source_names = merge_metadata.get("source_names") or {}
    conflicts = merge_metadata.get("conflicts") or {}
    source_id = field_sources.get(field_name)
    return {
        "source_id": source_id,
        "source_name": source_names.get(source_id, source_id) if source_id is not None else None,
        "from_secondary": source_id is not None and source_id != _primary_source_id(merge_metadata.get("source_order") or []),
        "conflicts": conflicts.get(field_name, []),
    }


def _source_rows(payload: Any, items_path: str | None) -> list[dict[str, Any]]:
    data = payload
    if items_path:
        for part in items_path.split("."):
            if not isinstance(data, dict) or part not in data:
                raise DirectRunError(f"Configured items_path '{items_path}' was not found in source response")
            data = data[part]

    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("items", "data", "results", "rows"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
        else:
            rows = [data]
    else:
        raise DirectRunError("Source response must be a JSON object or array")

    if not all(isinstance(row, dict) for row in rows):
        raise DirectRunError("Source rows must be JSON objects")
    return rows


def _pick_value(row: dict[str, Any], source_field: str | list[str] | None) -> Any:
    if source_field is None:
        return None
    if isinstance(source_field, str):
        return row.get(source_field)
    if isinstance(source_field, list):
        for field in source_field:
            if field in row:
                return row.get(field)
    return None


def _normalize_row(row: dict[str, Any], field_map: dict[str, Any] | None) -> dict[str, Any]:
    if not field_map:
        return dict(row)

    normalized = dict(row)
    for target_field, source_field in field_map.items():
        normalized[target_field] = _pick_value(row, source_field)
    return normalized


def _request_source_payload(config: dict[str, Any]) -> Any:
    url = config.get("url")
    if not url:
        raise DirectRunError("Data source config must include a source URL")

    try:
        request_kwargs: dict[str, Any] = {
            "headers": config.get("headers") or {},
            "timeout": 30,
        }
        if config.get("params") is not None:
            request_kwargs["params"] = config.get("params")
        if config.get("body") is not None:
            request_kwargs["json"] = config.get("body")

        response = httpx.request(
            str(config.get("method", "GET")).upper(),
            url,
            **request_kwargs,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise DirectRunError(f"Source request failed with HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise DirectRunError("Source request failed") from exc

    try:
        return response.json()
    except ValueError as exc:
        raise DirectRunError("Source response was not valid JSON") from exc


def _unique_key_for_row(row: dict[str, Any], *, unique_key_field: str | None, index: int) -> str:
    candidates = [unique_key_field, "unique_key", "id", "uuid", "code", "slug"]
    for candidate in candidates:
        if candidate and row.get(candidate) is not None:
            return str(row[candidate])
    return f"row-{index + 1}"


def _raw_text_for_row(source_row: dict[str, Any], text_field: str | None) -> str:
    if text_field and source_row.get(text_field) is not None:
        return str(source_row[text_field])
    return json.dumps(source_row, ensure_ascii=False)


def _normalize_country_alias(country: str, config: dict[str, Any]) -> str:
    aliases = config.get("country_aliases") or {}
    if not isinstance(aliases, dict):
        raise DirectRunError("country_aliases must be an object when provided")

    normalized_country = country.strip()
    alias = aliases.get(normalized_country)
    if alias is None:
        alias = aliases.get(normalized_country.lower())
    if alias is None:
        return normalized_country
    return str(alias).strip() or normalized_country



def _resolve_source_config(source: DataSource | object, *, country: str | None = None) -> tuple[str, dict[str, Any]]:
    config = dict(getattr(source, "config", None) or {})
    source_type = str(config.get("source_type", "json_api")).lower()
    supported_source_types = {"json_api", "escaped_jsonld_item_list"}
    if source_type not in supported_source_types:
        raise DirectRunError(f"Unsupported source_type '{source_type}'")

    if not config.get("url"):
        url_template = config.get("url_template")
        if url_template is None:
            raise DirectRunError("Data source config must include either url or url_template")
        if not isinstance(url_template, str) or not url_template.strip():
            raise DirectRunError("url_template must be a non-empty string when provided")
        if not country or not country.strip():
            raise DirectRunError("Country is required to resolve this data source")

        country_name = _normalize_country_alias(country, config)
        country_query = quote_plus(country_name)
        try:
            config["url"] = url_template.format(
                country=country_name,
                country_name=country_name,
                country_query=country_query,
            )
        except KeyError as exc:
            raise DirectRunError(f"url_template contains an unsupported placeholder: {exc.args[0]}") from exc

    return source_type, config



def _validate_source_config(config: dict[str, Any]) -> str:
    source_type = str(config.get("source_type", "json_api")).lower()
    supported_source_types = {"json_api", "escaped_jsonld_item_list"}
    if source_type not in supported_source_types:
        raise DirectRunError(f"Unsupported source_type '{source_type}'")
    if not config.get("url") and not config.get("url_template"):
        raise DirectRunError("Data source config must include either a source URL or url_template")
    if (field_map := config.get("field_map")) is not None and not isinstance(field_map, dict):
        raise DirectRunError("field_map must be an object when provided")
    if (items_path := config.get("items_path")) is not None and not isinstance(items_path, str):
        raise DirectRunError("items_path must be a string when provided")
    if (unique_key_field := config.get("unique_key_field")) is not None and not isinstance(unique_key_field, str):
        raise DirectRunError("unique_key_field must be a string when provided")
    if (text_field := config.get("text_field")) is not None and not isinstance(text_field, str):
        raise DirectRunError("text_field must be a string when provided")
    return source_type



def _load_json_api_source(config: dict[str, Any]) -> PreparedSource:
    payload = _request_source_payload(config)
    rows = _source_rows(payload, config.get("items_path"))
    field_map = config.get("field_map") or {}
    text_field = config.get("text_field")
    unique_key_field = config.get("unique_key_field")

    prepared_rows = [
        PreparedRow(
            normalized=_normalize_row(row, field_map),
            raw_payload=dict(row),
            raw_text=_raw_text_for_row(row, text_field),
            unique_key=_unique_key_for_row(row, unique_key_field=unique_key_field, index=index),
        )
        for index, row in enumerate(rows)
    ]
    return PreparedSource(source_type="json_api", rows=prepared_rows)


def _prepared_source_from_rows(*, source_type: str, rows: list[dict[str, Any]], config: dict[str, Any]) -> PreparedSource:
    field_map = config.get("field_map") or {}
    text_field = config.get("text_field")
    unique_key_field = config.get("unique_key_field")
    return PreparedSource(
        source_type=source_type,
        rows=[
            PreparedRow(
                normalized=_normalize_row(row, field_map),
                raw_payload=dict(row),
                raw_text=_raw_text_for_row(row, text_field),
                unique_key=_unique_key_for_row(row, unique_key_field=unique_key_field, index=index),
            )
            for index, row in enumerate(rows)
        ],
    )


def fetch_source_rows(source: DataSource | object, *, country: str | None = None) -> list[dict[str, Any]]:
    source_type, resolved_config = _resolve_source_config(source, country=country)
    _validate_source_config(resolved_config)
    if source_type == "json_api":
        return [prepared.normalized for prepared in _load_json_api_source(resolved_config).rows]
    if source_type == "escaped_jsonld_item_list":
        return [
            prepared.normalized
            for prepared in _prepared_source_from_rows(
                source_type=source_type,
                rows=load_escaped_jsonld_item_list(resolved_config),
                config=resolved_config,
            ).rows
        ]
    raise DirectRunError(f"Unsupported source_type '{source_type}'")



def prepare_source_rows(source: DataSource | object, *, country: str | None = None) -> PreparedSource:
    source_type, resolved_config = _resolve_source_config(source, country=country)
    _validate_source_config(resolved_config)
    if source_type == "json_api":
        return _load_json_api_source(resolved_config)
    if source_type == "escaped_jsonld_item_list":
        return _prepared_source_from_rows(
            source_type=source_type,
            rows=load_escaped_jsonld_item_list(resolved_config),
            config=resolved_config,
        )
    raise DirectRunError(f"Unsupported source_type '{source_type}'")


def _merged_raw_text(parts: list[str]) -> str:
    return "\n\n".join(part for part in parts if part)


def _merge_prepared_sources(sources: list[tuple[object, PreparedSource]]) -> list[MergedPreparedRow]:
    merged_rows: dict[str, MergedPreparedRow] = {}
    source_catalog = {str(source.id): _merge_source_catalog(source) for source, _prepared_source in sources}
    source_order = [str(source.id) for source, _prepared_source in sources]
    source_names = _merge_source_names(source_order, source_catalog)

    for source, prepared_source in sources:
        source_id = str(source.id)
        source_name = source_names.get(source_id, source_id)
        for prepared_row in prepared_source.rows:
            merge_key = _merge_key_for_row(prepared_row)
            existing = merged_rows.get(merge_key)
            if existing is None:
                field_sources = {
                    field_name: source_id
                    for field_name, field_value in prepared_row.normalized.items()
                    if not field_name.startswith("_") and not _is_empty_value(field_value)
                }
                conflicts: dict[str, list[dict[str, Any]]] = {}
                merge_metadata = _merge_metadata_payload(
                    source_order=source_order,
                    field_sources=field_sources,
                    conflicts=conflicts,
                    source_names=source_names,
                )
                merged_rows[merge_key] = MergedPreparedRow(
                    source_id=source_id,
                    unique_key=prepared_row.unique_key,
                    normalized=dict(prepared_row.normalized),
                    raw_payload=_build_merged_raw_payload(
                        normalized=dict(prepared_row.normalized),
                        source_payloads={source_id: dict(prepared_row.raw_payload)},
                        merge_metadata=merge_metadata,
                    ),
                    raw_text=prepared_row.raw_text,
                    merge_metadata=merge_metadata,
                    source_order=source_order,
                    source_names=source_names,
                    field_sources=field_sources,
                    conflicts=conflicts,
                    source_notes=_merge_source_metadata_map(source_order, source_catalog, "note"),
                    source_types=_merge_source_metadata_map(source_order, source_catalog, "type"),
                    source_roles=_merge_source_metadata_map(source_order, source_catalog, "role"),
                    source_labels=_merge_source_metadata_map(source_order, source_catalog, "label"),
                    source_countries=_merge_source_metadata_map(source_order, source_catalog, "country"),
                    source_supported_fields=_merge_source_metadata_map(source_order, source_catalog, "supported_fields"),
                    source_critical_fields=_merge_source_metadata_map(source_order, source_catalog, "critical_fields"),
                    source_configs=_merge_source_metadata_map(source_order, source_catalog, "config"),
                )
                continue

            merged_normalized = dict(existing.normalized)
            for field_name, field_value in prepared_row.normalized.items():
                _merge_field(
                    field_name=field_name,
                    incoming_value=field_value,
                    source_id=source_id,
                    source_name=source_name,
                    merged_normalized=merged_normalized,
                    field_sources=existing.field_sources,
                    conflicts=existing.conflicts,
                )

            source_payloads = dict(_merged_raw_source_payload(existing.raw_payload))
            source_payloads[source_id] = dict(prepared_row.raw_payload)
            merge_metadata = _merge_metadata_payload(
                source_order=existing.source_order,
                field_sources=existing.field_sources,
                conflicts=existing.conflicts,
                source_names=existing.source_names,
            )

            merged_rows[merge_key] = MergedPreparedRow(
                source_id=existing.source_id,
                unique_key=existing.unique_key,
                normalized=merged_normalized,
                raw_payload=_build_merged_raw_payload(
                    normalized=merged_normalized,
                    source_payloads=source_payloads,
                    merge_metadata=merge_metadata,
                ),
                raw_text=_merged_raw_text([existing.raw_text, prepared_row.raw_text]),
                merge_metadata=merge_metadata,
                source_order=existing.source_order,
                source_names=existing.source_names,
                field_sources=existing.field_sources,
                conflicts=existing.conflicts,
                source_notes=existing.source_notes,
                source_types=existing.source_types,
                source_roles=existing.source_roles,
                source_labels=existing.source_labels,
                source_countries=existing.source_countries,
                source_supported_fields=existing.source_supported_fields,
                source_critical_fields=existing.source_critical_fields,
                source_configs=existing.source_configs,
            )

    return list(merged_rows.values())


def _load_raw_record(db: Session, raw_record_id: str) -> RawRecord | object:
    raw_record = db.query(RawRecord).filter(RawRecord.id == raw_record_id).one_or_none()
    if raw_record is None:
        raise DirectRunError("Raw record could not be loaded after ingest")
    return raw_record


def _template_columns_for_job(db: Session, job: CrawlJob | object) -> list[dict[str, Any]]:
    template_id = getattr(job, "clean_template_id", None)
    if template_id is None:
        return []
    try:
        template = db.query(CleanTemplate).filter(CleanTemplate.id == template_id).one_or_none()
    except Exception:
        return []
    columns = getattr(template, "columns", None) if template is not None else None
    return [dict(column) for column in columns if isinstance(column, dict)] if isinstance(columns, list) else []


def _source_stub_from_bundle(bundle: DiscoverySourceBundle) -> object:
    return type(
        "DiscoverySourceStub",
        (),
        {
            "id": bundle.source_id,
            "source_name": bundle.source_name,
            "country": "",
            "supported_fields": [],
            "critical_fields": [],
            "config": {"source_type": "prompt_discovery" if bundle.source_id == "prompt-discovery" else "discovery_bundle", "role": "official" if bundle.source_id != "prompt-discovery" else "reference", "trust_level": "medium"},
        },
    )()


def _persisted_source_for_plan_entry(db: Session, entry: dict[str, Any], *, country: str) -> DataSource:
    source_name = str(entry.get("name") or entry.get("id") or "Catalog source")
    source_config = dict(entry.get("config") or {})
    existing = (
        db.query(DataSource)
        .filter(
            DataSource.country == country,
            DataSource.source_name == source_name,
        )
        .one_or_none()
    )
    if existing is None:
        existing = DataSource(
            country=country,
            source_name=source_name,
            supported_fields=list(entry.get("supported_fields") or []),
            critical_fields=list(entry.get("critical_fields") or []),
            config=source_config,
        )
    else:
        existing.supported_fields = list(entry.get("supported_fields") or [])
        existing.critical_fields = list(entry.get("critical_fields") or [])
        existing.config = source_config
    db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing


def _plan_entries(discovery_input: dict[str, Any] | None, *, plan_key: str) -> list[dict[str, Any]]:
    payload = discovery_input or {}
    plan = payload.get(plan_key) if isinstance(payload, dict) else None
    if isinstance(plan, dict):
        sources = plan.get("sources")
        if isinstance(sources, list):
            return [source for source in sources if isinstance(source, dict)]
    return []


def _trusted_source_plan_entries(job: CrawlJob | object) -> list[dict[str, Any]]:
    discovery_input = getattr(job, "discovery_input", None) or {}
    planned_sources = _plan_entries(discovery_input, plan_key="source_plan")
    if planned_sources:
        return planned_sources
    resolved = build_trusted_source_discovery_input(str(getattr(job, "country", "") or "")).get("source_plan") or {}
    fallback_sources = resolved.get("sources") if isinstance(resolved, dict) else []
    return [source for source in fallback_sources if isinstance(source, dict)] if isinstance(fallback_sources, list) else []


def _supplemental_source_plan_entries(job: CrawlJob | object) -> list[dict[str, Any]]:
    discovery_input = getattr(job, "discovery_input", None) or {}
    planned_sources = _plan_entries(discovery_input, plan_key="supplemental_plan")
    if planned_sources:
        return planned_sources
    resolved = build_supplemental_discovery_input(str(getattr(job, "country", "") or "")).get("supplemental_plan") or {}
    fallback_sources = resolved.get("sources") if isinstance(resolved, dict) else []
    return [source for source in fallback_sources if isinstance(source, dict)] if isinstance(fallback_sources, list) else []


def _resolved_plan_sources(
    db: Session,
    entries: list[dict[str, Any]],
    *,
    country: str,
    focus_fields: list[str] | tuple[str, ...] | None = None,
) -> list[tuple[object, PreparedSource]]:
    resolved_sources: list[tuple[object, PreparedSource]] = []
    source_errors: list[str] = []
    for entry in entries:
        source = _persisted_source_for_plan_entry(db, entry, country=country)
        source_name = str(getattr(source, "source_name", None) or entry.get("name") or entry.get("id") or "Catalog source")
        try:
            bundle = fetch_discovery_bundle_from_source(source, country=country, focus_fields=focus_fields)
        except Exception as exc:
            source_errors.append(f"{source_name}: {exc}")
            logger.warning("Skipping crawl source %s after fetch failure: %s", source_name, exc)
            continue
        resolved_sources.append(
            (
                source,
                _prepared_source_from_bundle(bundle),
            )
        )
    if entries and not resolved_sources and source_errors:
        raise DirectRunError(f"All configured sources failed: {'; '.join(source_errors)}")
    return resolved_sources


def _resolved_catalog_sources(db: Session, job: CrawlJob | object) -> list[tuple[object, PreparedSource]]:
    country = str(getattr(job, "country", "") or "")
    return _resolved_plan_sources(db, _trusted_source_plan_entries(job), country=country, focus_fields=list(getattr(job, "critical_fields", []) or []))


def _resolved_supplemental_sources(db: Session, job: CrawlJob | object) -> list[tuple[object, PreparedSource]]:
    country = str(getattr(job, "country", "") or "")
    return _resolved_plan_sources(db, _supplemental_source_plan_entries(job), country=country, focus_fields=list(getattr(job, "critical_fields", []) or []))


def _prepared_source_from_bundle(bundle: DiscoverySourceBundle) -> PreparedSource:
    return PreparedSource(
        source_type="discovery_bundle",
        rows=[
            PreparedRow(
                normalized=dict(row.normalized),
                raw_payload=dict(row.raw_payload),
                raw_text=row.raw_text,
                unique_key=row.unique_key,
            )
            for row in bundle.rows
        ],
    )


def _resolve_discovery_sources(db: Session, *, job: CrawlJob | object) -> list[tuple[object, PreparedSource]]:
    crawl_mode = getattr(job, "crawl_mode", "trusted_sources")
    discovery_input = getattr(job, "discovery_input", None) or {}

    if crawl_mode == "prompt_discovery":
        prompt_text = str(discovery_input.get("prompt_text") or "").strip()
        if not prompt_text:
            raise DirectRunError("Prompt discovery mode requires discovery_input.prompt_text")
        settings = get_settings()
        if not settings.has_gemini_api_key():
            raise DirectRunError("GEMINI_API_KEY is required for prompt discovery mode")
        try:
            prompt_result = discover_universities_from_prompt(
                PromptDiscoveryRequest(
                    country=getattr(job, "country", ""),
                    critical_fields=list(getattr(job, "critical_fields", []) or []),
                    prompt_text=prompt_text,
                ),
                client=build_gemini_client(),
            )
        except GeminiRateLimitError as exc:
            resolved_sources = _resolved_catalog_sources(db, job)
            if resolved_sources:
                logger.warning(
                    "Prompt discovery hit Gemini rate limits for country %s; falling back to trusted-source catalog.",
                    getattr(job, "country", ""),
                )
                return resolved_sources
            raise DirectRunError("Prompt discovery is temporarily unavailable because all configured Gemini API keys are rate-limited") from exc
        except Exception as exc:
            raise DirectRunError("Prompt discovery failed before crawl execution") from exc

        bundle = prompt_result_to_bundle(prompt_result)
        return [(_source_stub_from_bundle(bundle), _prepared_source_from_bundle(bundle))]

    if crawl_mode == "supplemental_discovery":
        resolved_sources = _resolved_supplemental_sources(db, job)
        if not resolved_sources:
            raise DirectRunError(f"No supplemental coverage plan is configured for {getattr(job, 'country', '')}")
        return resolved_sources

    if not getattr(job, "source_ids", None):
        resolved_sources = _resolved_catalog_sources(db, job)
        if not resolved_sources:
            raise DirectRunError(f"No trusted-source plan is configured for {getattr(job, 'country', '')}")
        return resolved_sources

    sources = db.query(DataSource).filter(DataSource.id.in_(job.source_ids)).all()
    if len(sources) != len(set(job.source_ids)):
        raise DirectRunError("One or more crawl job sources could not be loaded")
    resolved_sources: list[tuple[object, PreparedSource]] = []
    for source in sources:
        source_config = dict(getattr(source, "config", None) or {})
        source_type = str(source_config.get("source_type", "json_api")).lower()
        if source_type in {"json_api", "escaped_jsonld_item_list"}:
            resolved_sources.append((source, prepare_source_rows(source, country=getattr(job, "country", None))))
            continue
        resolved_sources.append(
            (
                source,
                _prepared_source_from_bundle(
                    fetch_discovery_bundle_from_source(
                        source,
                        country=getattr(job, "country", None),
                        focus_fields=list(getattr(job, "critical_fields", []) or []),
                    )
                ),
            )
        )
    return resolved_sources


def run_crawl_job_direct(db: Session, *, job: CrawlJob | object) -> DirectRunResult:

    job.status = "CRAWLING"
    job.progress = _build_progress(total_records=0, crawled=0, extracted=0, needs_review=0, cleaned=0)
    db.add(job)
    db.commit()
    db.refresh(job)

    total_records = 0
    crawled = 0
    extracted = 0
    needs_review = 0
    cleaned = 0
    skipped = 0
    clean_candidates = 0
    approved = 0
    rejected = 0
    processed = 0

    prepared_sources = _resolve_discovery_sources(db, job=job)
    merged_rows = _merge_prepared_sources(prepared_sources)
    template_columns = _template_columns_for_job(db, job)
    total_records = len(merged_rows)
    crawled = len(merged_rows)

    job.status = "EXTRACTING"
    job.progress = _build_progress(
        total_records=total_records,
        crawled=crawled,
        extracted=0,
        needs_review=0,
        cleaned=0,
        skipped=0,
        clean_candidates=0,
        approved=0,
        rejected=0,
        processed=0,
    )
    db.add(job)
    db.commit()

    def persist_progress() -> None:
        job.progress = _build_progress(
            total_records=total_records,
            crawled=crawled,
            extracted=extracted,
            needs_review=needs_review,
            cleaned=cleaned,
            skipped=skipped,
            clean_candidates=clean_candidates,
            approved=approved,
            rejected=rejected,
            processed=processed,
        )
        db.add(job)
        db.commit()

    for index, prepared_row in enumerate(merged_rows, start=1):
        try:
            target_fields = _target_fields_for_row(prepared_row, job.critical_fields, template_columns)
            raw_result = upsert_raw_record(
                db,
                job_id=job.id,
                source_id=prepared_row.source_id,
                unique_key=prepared_row.unique_key,
                raw_payload=prepared_row.raw_payload,
                record_hash=None,
            )
            if not raw_result.changed:
                existing_clean = _clean_record_for_job_key(db, job_id=job.id, unique_key=prepared_row.unique_key)
                if existing_clean is not None and _clean_record_covers_fields(existing_clean, prepared_row, target_fields):
                    skipped += 1
                    processed += 1
                    clean_candidates += 1
                    if getattr(existing_clean, "status", None) != "REJECTED":
                        cleaned += 1
                    approved_inc, needs_review_inc, rejected_inc = _count_clean_status(str(getattr(existing_clean, "status", "NEEDS_REVIEW")))
                    approved += approved_inc
                    needs_review += needs_review_inc
                    rejected += rejected_inc
                    persist_progress()
                    continue

            raw_record = _load_raw_record(db, raw_result.raw_record_id)
            extractor_output = _extractor_output_for_row(job, prepared_row, template_columns)
            extracted += 1
            processed += 1
            extracted_values = {field: value.value for field, value in extractor_output.critical_fields.items()}
            required_fields = required_fields_for_job(job, template_columns)
            rule_validation = validate_critical_fields(extracted_values, required_fields=required_fields)
            judge_output = _judge_output_for_row(job, prepared_row, extractor_output, rule_validation, required_fields)

            _annotate_judge_output(
                judge_output=judge_output,
                merge_metadata=prepared_row.merge_metadata,
                extracted_values=extracted_values,
            )
            scoring = calculate_weighted_confidence(judge_output, required_fields=required_fields)
            ai_log = _log_ai_extraction_with_merge(
                db,
                raw_record_id=raw_result.raw_record_id,
                extractor_output=extractor_output,
                judge_output=judge_output,
                scoring=scoring,
                merge_metadata=prepared_row.merge_metadata,
            )
            clean_result = generate_clean_record(db, raw_record=raw_record, ai_log=ai_log)
            clean_candidates += 1
            if clean_result.clean_record.status != "REJECTED":
                cleaned += 1
            approved_inc, needs_review_inc, rejected_inc = _count_clean_status(clean_result.clean_record.status)
            approved += approved_inc
            needs_review += needs_review_inc
            rejected += rejected_inc
        except Exception:
            logger.exception(
                "Skipping row %s/%s for job %s after processing failure. unique_key=%s",
                index,
                total_records,
                getattr(job, "id", "unknown"),
                prepared_row.unique_key,
            )
            db.rollback()
            skipped += 1
            rejected += 1
            processed += 1

        persist_progress()

    status = _status_from_progress(
        total_records=total_records,
        approved=approved,
        needs_review=needs_review,
        processed=processed,
        rejected=rejected,
    )

    job.status = status
    job.progress = _build_progress(
        total_records=total_records,
        crawled=crawled,
        extracted=extracted,
        needs_review=needs_review,
        cleaned=cleaned,
        skipped=skipped,
        clean_candidates=clean_candidates,
        approved=approved,
        rejected=rejected,
        processed=processed,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    return DirectRunResult(
        total_records=total_records,
        crawled=crawled,
        extracted=extracted,
        needs_review=needs_review,
        cleaned=cleaned,
        skipped=skipped,
        clean_candidates=clean_candidates,
        approved=approved,
        rejected=rejected,
        processed=processed,
        status=status,
    )


    def generate_json(self, *, prompt: str) -> str:
        del prompt
        payload = {
            "critical_fields": {
                field: {
                    "value": self._schema_value(self.row.get(field)),
                    "confidence": 1.0 if self.row.get(field) is not None else 0.0,
                    "source_excerpt": None if self.row.get(field) is None else str(self._schema_value(self.row.get(field))),
                }
                for field in self.critical_fields
            },
            "extraction_notes": ["AI assist disabled; values copied directly from source row."],
        }
        return json.dumps(payload, ensure_ascii=False)


class RuleBasedJudgeClient:
    def __init__(self, extractor_output: AIExtractorOutput, required_fields: list[str]) -> None:
        self.extractor_output = extractor_output
        self.required_fields = required_fields

    def generate_json(self, *, prompt: str) -> str:
        del prompt
        extracted = {field: value.value for field, value in self.extractor_output.critical_fields.items()}
        validation = validate_critical_fields(extracted, required_fields=self.required_fields)
        fields_validation = {}
        for field in extracted:
            matching_issue = next((issue for issue in validation.issues if issue.field == field), None)
            fields_validation[field] = {
                "is_correct": matching_issue is None,
                "corrected_value": None,
                "confidence": 96 if matching_issue is None else 60,
                "reason": "Matches source" if matching_issue is None else matching_issue.message,
            }
        payload = {
            "fields_validation": fields_validation,
            "overall_confidence": 96 if validation.is_valid else 60,
            "status": "APPROVED" if validation.is_valid else "NEEDS_REVIEW",
            "summary": "Rule-based validation completed.",
        }
        return json.dumps(payload, ensure_ascii=False)


@dataclass
class PreparedRow:
    normalized: dict[str, Any]
    raw_payload: dict[str, Any]
    raw_text: str
    unique_key: str


@dataclass
class _SourceStub:
    id: str
    source_name: str
    config: dict[str, Any]


class _PromptDiscoveryClient:
    def generate_json(self, *, prompt: str) -> str:
        gemini_client = build_gemini_client()
        return gemini_client.generate_json(prompt=prompt)


class _GeminiDiscoveryClientWithFallback:
    def __init__(self, *, allow_rate_limit_fallback: bool) -> None:
        self.allow_rate_limit_fallback = allow_rate_limit_fallback

    def generate_json(self, *, prompt: str) -> str:
        last_error: GeminiRateLimitError | None = None
        for model_name in (None, "gemini-2.5-flash", "gemini-2.5-pro"):
            try:
                gemini_client = build_gemini_client(model_name=model_name)
                return gemini_client.generate_json(prompt=prompt)
            except GeminiRateLimitError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise DirectRunError("Prompt discovery failed to initialize a Gemini client")


class _EscapedJsonldSourceError(DirectRunError):
    pass


class _MergeBucket:
    def __init__(self, *, source_id: str, normalized: dict[str, Any], raw_payload: dict[str, Any], raw_text: str, unique_key: str) -> None:
        self.source_id = source_id
        self.normalized = normalized
        self.raw_payload = raw_payload
        self.raw_text = raw_text
        self.unique_key = unique_key
        self.field_sources: dict[str, str] = {field: source_id for field, value in normalized.items() if value not in (None, "", [], {})}
        self.conflicts: dict[str, list[dict[str, Any]]] = {}
        self.sources: dict[str, dict[str, Any]] = {source_id: raw_payload}
        self.raw_texts: list[str] = [raw_text] if raw_text else []

    def merge(self, *, source_id: str, normalized: dict[str, Any], raw_payload: dict[str, Any], raw_text: str) -> None:
        self.sources[source_id] = raw_payload
        if raw_text:
            self.raw_texts.append(raw_text)

        for field, incoming_value in normalized.items():
            current_value = self.normalized.get(field)
            if current_value in (None, "", [], {}):
                if incoming_value not in (None, "", [], {}):
                    self.normalized[field] = incoming_value
                    self.field_sources[field] = source_id
                continue

            if incoming_value in (None, "", [], {}):
                continue

            if current_value != incoming_value:
                self.conflicts.setdefault(field, []).append(
                    {
                        "source_id": source_id,
                        "value": incoming_value,
                    }
                )

    def to_row(self) -> MergedPreparedRow:
        merged_payload = dict(self.raw_payload)
        merged_payload["sources"] = self.sources
        merged_payload["_merge"] = {
            "field_sources": self.field_sources,
            "conflicts": self.conflicts,
        }
        return MergedPreparedRow(
            source_id=self.source_id,
            normalized=self.normalized,
            raw_payload=merged_payload,
            raw_text="\n\n".join(self.raw_texts),
            unique_key=self.unique_key,
            merge_metadata=merged_payload["_merge"],
        )
































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































