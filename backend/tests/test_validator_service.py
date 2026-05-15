from app.services.validator import validate_critical_fields


def test_validator_passes_valid_fields() -> None:
    result = validate_critical_fields(
        {
            "name": "Example University",
            "admissions_contact": "+84 903 123 456",
            "website": "https://example.edu",
            "email": "info@example.edu",
        },
        required_fields=["name", "website"],
    )

    assert result.is_valid is True
    assert result.issues == []


def test_validator_flags_required_missing_and_format_errors() -> None:
    result = validate_critical_fields(
        {
            "name": "",
            "email": "bad-email",
            "website": "example.edu",
            "admissions_contact": "abc",
        },
        required_fields=["name", "website"],
    )

    codes = [issue.code for issue in result.issues]
    assert result.is_valid is False
    assert "required_missing" in codes
    assert "invalid_email" in codes
    assert "invalid_url" in codes
    assert "invalid_phone" in codes
