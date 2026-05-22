from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.schemas.ai_output import AIExtractorOutput, AIJudgeOutput
from app.services.validator import ValidationResult
from app.services.prompt_rules import build_field_instructions


class AIJudgeClientProtocol(Protocol):
    def generate_json(self, *, prompt: str) -> str: ...


@dataclass
class JudgeRequest:
    raw_text: str
    extractor_output: AIExtractorOutput
    rule_validation: ValidationResult | None = None
    country: str | None = None
    location_code: int | None = None
    critical_fields: list[str] | None = None


class AIJudgeConfigurationError(RuntimeError):
    pass


class AIJudgeParseError(ValueError):
    pass


def build_judge_prompt(request: JudgeRequest) -> str:
    extractor_json = request.extractor_output.model_dump_json(ensure_ascii=False)
    rules_text = build_field_instructions(country=request.country, location_code=request.location_code)
    rule_summary = (
        json.dumps(
            [
                {"field": issue.field, "code": issue.code, "message": issue.message}
                for issue in request.rule_validation.issues
            ],
            ensure_ascii=False,
        )
        if request.rule_validation
        else "[]"
    )
    critical_fields_json = json.dumps(request.critical_fields or [], ensure_ascii=False)
    
    return (
        "You are a data QA validator. Compare the structured extraction against the raw text and provided metadata. "
        "Review each extracted field for correctness, evidence support, and output-format safety. "
        "Crucially, cross-check the data against the raw text and external links to verify if the information is TRUTHFUL and has solid evidence. "
        "If a value is hallucinated, fabricated, or lacks evidence, you MUST mark it as incorrect (`is_correct`: false). "
        "A field is correct only when its value is directly supported by source_excerpt, the raw text, or a valid evidence URL. "
        "Exception: if evidence_source is 'ai_enrichment_model_memory', treat it as model-memory enrichment and approve only if the value is stable, non-sensitive, passes the field rules, and confidence is very high; otherwise set corrected_value to null. "
        "For financials, accept only annual tuition/fee/cost amounts or ranges (format: Local Currency ($USD in brackets)). If the value is filled and matches this format, and is supported by a valid evidence_url (like collegedunia, shiksha, or the official school website), approve it immediately. Generic scholarship, financial-aid, or fee-policy text without a money amount is incorrect. "
        "For admissions_phone, reject dummy or placeholder values such as 123456, sequential digits, repeated digits, and any phone value not supported by admissions/contact evidence. "
        "If a non-null value is not supported by evidence, mark it incorrect and set corrected_value to null unless the raw text supports a better value. "
        "Propose corrected_value when needed, and assign confidence 0-100. "
        f"\nCRITICAL FIELDS: {critical_fields_json}\n"
        "These are the focus fields for the dataset. You must adhere to the following STATUS RULES:\n"
        "1. REJECTED: If the raw text is completely irrelevant (e.g., a parked domain or non-university page) and essential identity fields are missing, set status to 'REJECTED'.\n"
        "2. APPROVED: If all CRITICAL fields are acceptable, format-valid, and supported by source excerpts or valid evidence URLs, you MUST set status to 'APPROVED'. Be generous in auto-approving if the core identity of the university is correct and no critical fields are hallucinated. We want to minimize human review and only prompt review when there is a critical format error or clear hallucination.\n"
        "3. NEEDS_REVIEW: Only if a CRITICAL field is clearly hallucinated, has critical format violations (like non-digit values in numeric fields), or is missing without any evidence, set status to 'NEEDS_REVIEW'.\n"
        "4. If an OPTIONAL field (not in CRITICAL FIELDS) lacks evidence or has an error, just set its `is_correct` to false and `corrected_value` to null, BUT KEEP the overall status as 'APPROVED' (do not flag the record for review for optional fields).\n"
        "Return strict JSON with this shape: "
        "{\"fields_validation\": {\"field_name\": {\"is_correct\": true|false, \"corrected_value\": ..., \"confidence\": 0-100, \"reason\": ...}}, \"overall_confidence\": 0-100, \"status\": \"APPROVED\"|\"NEEDS_REVIEW\"|\"REJECTED\", \"summary\": ...}. "
        f"\n{rules_text}\n"
        f"Rule validation findings: {rule_summary}. "
        f"Extractor output: {extractor_json}. "
        f"Raw text: {request.raw_text}"
    )


def parse_judge_output(payload: str) -> AIJudgeOutput:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AIJudgeParseError("AI judge returned invalid JSON") from exc

    try:
        return AIJudgeOutput.model_validate(data)
    except Exception as exc:
        raise AIJudgeParseError("AI judge output failed schema validation") from exc


def judge_extraction(
    request: JudgeRequest,
    *,
    client: AIJudgeClientProtocol,
) -> AIJudgeOutput:
    if getattr(client, "requires_api_key", True):
        settings = get_settings()
        has_gemini = bool(getattr(settings, "has_gemini_api_key", lambda: False)())
        has_anthropic = bool(getattr(settings, "has_anthropic_api_key", lambda: False)())
        if not has_gemini and not has_anthropic:
            raise AIJudgeConfigurationError("Provider API key is not configured")

    prompt = build_judge_prompt(request)
    response = client.generate_json(prompt=prompt)
    return parse_judge_output(response)
