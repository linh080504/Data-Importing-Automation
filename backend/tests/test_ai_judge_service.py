import pytest

from app.schemas.ai_output import AIExtractorOutput
from app.services.ai_judge import (
    AIJudgeConfigurationError,
    AIJudgeParseError,
    JudgeRequest,
    build_judge_prompt,
    judge_extraction,
    parse_judge_output,
)
from app.services.validator import validate_critical_fields


class FakeJudgeClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt = None

    def generate_json(self, *, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


def _extractor_output() -> AIExtractorOutput:
    return AIExtractorOutput.model_validate(
        {
            "critical_fields": {
                "website": {
                    "value": "https://example.edu",
                    "confidence": 0.91,
                    "source_excerpt": "https://example.edu",
                },
                "email": {
                    "value": "bad-email",
                    "confidence": 0.60,
                    "source_excerpt": "Contact: bad-email",
                },
            },
            "extraction_notes": [],
        }
    )


def test_build_judge_prompt_includes_rule_findings_and_extractor_output() -> None:
    rules = validate_critical_fields({"email": "bad-email", "website": "https://example.edu"}, required_fields=["website"])
    prompt = build_judge_prompt(JudgeRequest(raw_text="Contact: bad-email", extractor_output=_extractor_output(), rule_validation=rules))

    assert "Rule validation findings" in prompt
    assert "bad-email" in prompt
    assert "https://example.edu" in prompt


def test_parse_judge_output_validates_schema() -> None:
    payload = '{"fields_validation": {"website": {"is_correct": true, "corrected_value": null, "confidence": 96, "reason": "Matches source"}}, "overall_confidence": 90, "status": "APPROVED", "summary": "Valid"}'

    parsed = parse_judge_output(payload)

    assert parsed.status == "APPROVED"
    assert parsed.fields_validation["website"].confidence == 96


def test_parse_judge_output_rejects_invalid_json() -> None:
    with pytest.raises(AIJudgeParseError):
        parse_judge_output("not-json")


def test_judge_extraction_requires_gemini_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai_judge.get_settings",
        lambda: type("Settings", (), {"has_gemini_api_key": lambda self: False})(),
    )
    client = FakeJudgeClient("{}")

    with pytest.raises(AIJudgeConfigurationError) as exc_info:
        judge_extraction(
            JudgeRequest(raw_text="Example", extractor_output=_extractor_output()),
            client=client,
        )

    assert "GEMINI_API_KEY" in str(exc_info.value)
    assert "super-secret-gemini-key" not in str(exc_info.value)
    assert client.last_prompt is None



def test_judge_extraction_configuration_error_does_not_echo_real_key(monkeypatch) -> None:
    leaked_value = "super-secret-gemini-key"
    monkeypatch.setattr(
        "app.services.ai_judge.get_settings",
        lambda: type("Settings", (), {"has_gemini_api_key": lambda self: False, "loaded_value": leaked_value})(),
    )

    with pytest.raises(AIJudgeConfigurationError) as exc_info:
        judge_extraction(
            JudgeRequest(raw_text="Example", extractor_output=_extractor_output()),
            client=FakeJudgeClient("{}"),
        )

    assert leaked_value not in str(exc_info.value)



def test_parse_judge_output_error_message_does_not_echo_raw_payload() -> None:
    raw_payload = '{"fields_validation": '

    with pytest.raises(AIJudgeParseError) as exc_info:
        parse_judge_output(raw_payload)

    assert raw_payload not in str(exc_info.value)
    assert "invalid JSON" in str(exc_info.value)


def test_judge_extraction_returns_validated_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai_judge.get_settings",
        lambda: type("Settings", (), {"has_gemini_api_key": lambda self: True})(),
    )
    client = FakeJudgeClient(
        '{"fields_validation": {"email": {"is_correct": false, "corrected_value": "info@example.edu", "confidence": 82, "reason": "Invalid email corrected"}}, "overall_confidence": 84, "status": "NEEDS_REVIEW", "summary": "Email needs manual review"}'
    )

    result = judge_extraction(
        JudgeRequest(raw_text="Contact: bad-email", extractor_output=_extractor_output()),
        client=client,
    )

    assert result.status == "NEEDS_REVIEW"
    assert result.fields_validation["email"].corrected_value == "info@example.edu"
    assert client.last_prompt is not None
