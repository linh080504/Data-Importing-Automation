import pytest
from pydantic import ValidationError

from app.schemas.ai_output import AIExtractorOutput, AIJudgeOutput


def test_ai_extractor_output_accepts_structured_critical_fields() -> None:
    payload = {
        "critical_fields": {
            "name": {
                "value": "Example University",
                "confidence": 0.97,
                "source_excerpt": "Example University is located in...",
            },
            "website": {
                "value": "https://example.edu",
                "confidence": 0.91,
                "source_excerpt": "Visit https://example.edu",
            },
        },
        "extraction_notes": ["Website extracted from official footer"],
    }

    parsed = AIExtractorOutput.model_validate(payload)

    assert parsed.critical_fields["name"].value == "Example University"
    assert parsed.critical_fields["website"].confidence == 0.91


def test_ai_judge_output_accepts_validation_summary() -> None:
    payload = {
        "fields_validation": {
            "name": {
                "is_correct": True,
                "corrected_value": None,
                "confidence": 98,
                "reason": "Matches official source",
            },
            "address": {
                "is_correct": False,
                "corrected_value": "123 Main St, Hanoi",
                "confidence": 84,
                "reason": "Expanded abbreviated address",
            },
        },
        "overall_confidence": 91,
        "status": "APPROVED",
        "summary": "All required fields are acceptable",
    }

    parsed = AIJudgeOutput.model_validate(payload)

    assert parsed.overall_confidence == 91
    assert parsed.fields_validation["address"].corrected_value == "123 Main St, Hanoi"


def test_ai_extractor_output_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        AIExtractorOutput.model_validate(
            {
                "critical_fields": {
                    "name": {
                        "value": "Example University",
                        "confidence": 1.5,
                    }
                }
            }
        )


def test_ai_judge_output_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        AIJudgeOutput.model_validate(
            {
                "fields_validation": {},
                "overall_confidence": 50,
                "status": "MAYBE",
            }
        )
