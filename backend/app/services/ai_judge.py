from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.schemas.ai_output import AIExtractorOutput, AIJudgeOutput
from app.services.validator import ValidationResult


class AIJudgeClientProtocol(Protocol):
    def generate_json(self, *, prompt: str) -> str: ...


@dataclass
class JudgeRequest:
    raw_text: str
    extractor_output: AIExtractorOutput
    rule_validation: ValidationResult | None = None


class AIJudgeConfigurationError(RuntimeError):
    pass


class AIJudgeParseError(ValueError):
    pass


def build_judge_prompt(request: JudgeRequest) -> str:
    extractor_json = request.extractor_output.model_dump_json(ensure_ascii=False)
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
    return (
        "You are a data QA validator. Compare the structured extraction against the raw text. "
        "Review each extracted field for correctness, evidence support, and output-format safety. "
        "A field is correct only when its value is directly supported by source_excerpt or the raw text. "
        "If a non-null value is not supported by evidence, mark it incorrect and set corrected_value to null unless the raw text supports a better value. "
        "Propose corrected_value when needed, and assign confidence 0-100. "
        "Return strict JSON with this shape: "
        "{\"fields_validation\": {\"field_name\": {\"is_correct\": true|false, \"corrected_value\": ..., \"confidence\": 0-100, \"reason\": ...}}, \"overall_confidence\": 0-100, \"status\": \"APPROVED\"|\"NEEDS_REVIEW\"|\"REJECTED\", \"summary\": ...}. "
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
    settings = get_settings()
    if not settings.has_gemini_api_key():
        raise AIJudgeConfigurationError("GEMINI_API_KEY is not configured")

    prompt = build_judge_prompt(request)
    response = client.generate_json(prompt=prompt)
    return parse_judge_output(response)
