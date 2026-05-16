from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedFieldValue(BaseModel):
    value: str | int | float | bool | None
    confidence: float = Field(ge=0.0, le=1.0)
    source_excerpt: str | None = None
    evidence_url: str | None = None
    evidence_source: str | None = None
    evidence_required: bool = False


class AIExtractorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critical_fields: dict[str, ExtractedFieldValue]
    extraction_notes: list[str] = Field(default_factory=list)


class FieldValidationResult(BaseModel):
    is_correct: bool
    corrected_value: str | int | float | bool | None = None
    confidence: int = Field(ge=0, le=100)
    reason: str | None = None


class AIJudgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields_validation: dict[str, FieldValidationResult]
    overall_confidence: int = Field(ge=0, le=100)
    status: Literal["APPROVED", "NEEDS_REVIEW", "REJECTED"]
    summary: str | None = None
