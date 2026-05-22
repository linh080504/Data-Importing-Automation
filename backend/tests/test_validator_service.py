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
    assert "invalid_contact" in codes


def test_validator_rejects_placeholder_phone_and_generic_financials() -> None:
    result = validate_critical_fields(
        {
            "admissions_phone": "123456",
            "financials": "Tuition fees vary by program and are published annually.",
        }
    )

    codes = [issue.code for issue in result.issues]
    assert result.is_valid is False
    assert "invalid_phone" in codes
    assert "invalid_financials" in codes


def test_validator_accepts_source_ready_financials_and_contact_email() -> None:
    result = validate_critical_fields(
        {
            "admissions_contact": "admissions@example.edu",
            "admissions_phone": "+84 24 3869 4242",
            "financials": "Tuition fees range from 22,000,000 to 28,000,000 VND per year.",
        }
    )

    assert result.is_valid is True


def test_validator_rejects_generic_taxonomy_description() -> None:
    result = validate_critical_fields(
        {
            "description": "Private universities and private colleges are higher education institutions not operated by governments.",
        }
    )

    codes = [issue.code for issue in result.issues]
    assert result.is_valid is False
    assert "generic_content" in codes


def test_validator_rejects_country_mismatch_when_expected_country_is_set() -> None:
    result = validate_critical_fields(
        {
            "country": "Austria",
            "name": "Example University",
        },
        expected_country="Vietnam",
    )

    codes = [issue.code for issue in result.issues]
    assert result.is_valid is False
    assert "country_mismatch" in codes


def test_validator_accepts_country_match_aliases() -> None:
    result = validate_critical_fields(
        {
            "country": "Viet Nam",
            "name": "Example University",
        },
        expected_country="Vietnam",
    )

    assert result.is_valid is True
    assert result.issues == []
