from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings
from app.schemas.ai_output import AIExtractorOutput


class AIClientProtocol(Protocol):
    def generate_json(self, *, prompt: str) -> str: ...


@dataclass
class ExtractRequest:
    raw_text: str
    critical_fields: list[str]


class AIExtractorConfigurationError(RuntimeError):
    pass


class AIExtractorParseError(ValueError):
    pass


def build_extractor_prompt(request: ExtractRequest) -> str:
    fields_json = json.dumps(request.critical_fields, ensure_ascii=False)
    return (
        "You are a structured data extraction engine. "
        "Extract only the requested critical fields from the raw text. "
        "Return strict JSON with this shape: "
        "{\"critical_fields\": {\"field_name\": {\"value\": ..., \"confidence\": 0.0-1.0, \"source_excerpt\": ...}}, \"extraction_notes\": [...]} . "
        "Do not include any fields outside the requested list. "
        f"Requested critical fields: {fields_json}. "
        f"Raw text: {request.raw_text}"
    )


def parse_extractor_output(payload: str) -> AIExtractorOutput:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AIExtractorParseError("AI extractor returned invalid JSON") from exc

    try:
        return AIExtractorOutput.model_validate(data)
    except Exception as exc:
        raise AIExtractorParseError("AI extractor output failed schema validation") from exc


def extract_critical_fields(
    request: ExtractRequest,
    *,
    client: AIClientProtocol,
) -> AIExtractorOutput:
    settings = get_settings()
    if not settings.has_gemini_api_key():
        raise AIExtractorConfigurationError("GEMINI_API_KEY is not configured")

    prompt = build_extractor_prompt(request)
    response = client.generate_json(prompt=prompt)
    return parse_extractor_output(response)
