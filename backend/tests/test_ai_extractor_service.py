import pytest

from app.services.ai_extractor import (
    AIExtractorConfigurationError,
    AIExtractorParseError,
    ExtractRequest,
    build_extractor_prompt,
    extract_critical_fields,
    parse_extractor_output,
)


class FakeAIClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt = None

    def generate_json(self, *, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


def test_build_extractor_prompt_includes_requested_fields() -> None:
    request = ExtractRequest(raw_text="Example University website: https://example.edu", critical_fields=["name", "website"])

    prompt = build_extractor_prompt(request)

    assert "name" in prompt
    assert "website" in prompt
    assert "Example University" in prompt


def test_parse_extractor_output_validates_schema() -> None:
    payload = '{"critical_fields": {"name": {"value": "Example University", "confidence": 0.95, "source_excerpt": "Example University"}}, "extraction_notes": []}'

    parsed = parse_extractor_output(payload)

    assert parsed.critical_fields["name"].value == "Example University"


def test_parse_extractor_output_rejects_invalid_json() -> None:
    with pytest.raises(AIExtractorParseError):
        parse_extractor_output("not-json")


def test_extract_critical_fields_requires_gemini_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai_extractor.get_settings",
        lambda: type("Settings", (), {"has_gemini_api_key": lambda self: False})(),
    )
    client = FakeAIClient("{}")

    with pytest.raises(AIExtractorConfigurationError) as exc_info:
        extract_critical_fields(
            ExtractRequest(raw_text="Example", critical_fields=["name"]),
            client=client,
        )

    assert "GEMINI_API_KEY" in str(exc_info.value)
    assert "super-secret-gemini-key" not in str(exc_info.value)
    assert client.last_prompt is None



def test_extract_critical_fields_configuration_error_does_not_echo_real_key(monkeypatch) -> None:
    leaked_value = "super-secret-gemini-key"
    monkeypatch.setattr(
        "app.services.ai_extractor.get_settings",
        lambda: type("Settings", (), {"has_gemini_api_key": lambda self: False, "loaded_value": leaked_value})(),
    )

    with pytest.raises(AIExtractorConfigurationError) as exc_info:
        extract_critical_fields(
            ExtractRequest(raw_text="Example", critical_fields=["name"]),
            client=FakeAIClient("{}"),
        )

    assert leaked_value not in str(exc_info.value)



def test_parse_extractor_output_error_message_does_not_echo_raw_payload() -> None:
    raw_payload = '{"critical_fields": '

    with pytest.raises(AIExtractorParseError) as exc_info:
        parse_extractor_output(raw_payload)

    assert raw_payload not in str(exc_info.value)
    assert "invalid JSON" in str(exc_info.value)


def test_extract_critical_fields_returns_validated_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai_extractor.get_settings",
        lambda: type("Settings", (), {"has_gemini_api_key": lambda self: True})(),
    )
    client = FakeAIClient(
        '{"critical_fields": {"website": {"value": "https://example.edu", "confidence": 0.91, "source_excerpt": "https://example.edu"}}, "extraction_notes": ["from footer"]}'
    )

    result = extract_critical_fields(
        ExtractRequest(raw_text="Website: https://example.edu", critical_fields=["website"]),
        client=client,
    )

    assert result.critical_fields["website"].value == "https://example.edu"
    assert client.last_prompt is not None
