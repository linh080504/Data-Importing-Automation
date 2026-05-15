from app.services.import_readiness import evaluate_import_readiness


def _checks_by_key(result):
    return {check.key: check for check in result.checks}


def _blockers_by_key(result):
    return {blocker.key: blocker for blocker in result.blockers}


TEMPLATE_COLUMNS = [
    {"name": "name", "order": 1},
    {"name": "website", "order": 2},
    {"name": "slug", "order": 3},
]



def test_import_readiness_is_ready_when_required_fields_present_and_schema_matches() -> None:
    result = evaluate_import_readiness(
        clean_payload={
            "name": "Example University",
            "website": "https://example.edu",
            "slug": "example-university",
        },
        required_fields=["name", "website"],
        template_columns=TEMPLATE_COLUMNS,
        is_duplicate=False,
    )

    checks = _checks_by_key(result)
    assert result.is_ready is True
    assert result.blockers == []
    assert checks["required_critical_fields"].passed is True
    assert checks["duplicates"].passed is True
    assert checks["schema_match"].passed is True



def test_import_readiness_fails_when_required_fields_missing() -> None:
    result = evaluate_import_readiness(
        clean_payload={
            "name": "Example University",
            "website": "",
            "slug": "example-university",
        },
        required_fields=["name", "website"],
        template_columns=TEMPLATE_COLUMNS,
        is_duplicate=False,
    )

    checks = _checks_by_key(result)
    blockers = _blockers_by_key(result)
    assert result.is_ready is False
    assert checks["required_critical_fields"].passed is False
    assert checks["required_critical_fields"].blocker_count == 1
    assert blockers["required_critical_fields"].count == 1



def test_import_readiness_fails_for_duplicate_record() -> None:
    result = evaluate_import_readiness(
        clean_payload={
            "name": "Example University",
            "website": "https://example.edu",
            "slug": "example-university",
        },
        required_fields=["name", "website"],
        template_columns=TEMPLATE_COLUMNS,
        is_duplicate=True,
    )

    checks = _checks_by_key(result)
    blockers = _blockers_by_key(result)
    assert result.is_ready is False
    assert checks["duplicates"].passed is False
    assert checks["duplicates"].blocker_count == 1
    assert blockers["duplicates"].count == 1



def test_import_readiness_fails_for_schema_mismatch() -> None:
    result = evaluate_import_readiness(
        clean_payload={
            "name": "Example University",
            "website": "https://example.edu",
            "extra_field": "unexpected",
        },
        required_fields=["name", "website"],
        template_columns=TEMPLATE_COLUMNS,
        is_duplicate=False,
    )

    checks = _checks_by_key(result)
    blockers = _blockers_by_key(result)
    assert result.is_ready is False
    assert checks["schema_match"].passed is False
    assert checks["schema_match"].blocker_count == 2
    assert blockers["schema_match"].count == 2



def test_import_readiness_reports_multiple_blockers_together() -> None:
    result = evaluate_import_readiness(
        clean_payload={
            "name": "Example University",
            "website": None,
            "extra_field": "unexpected",
        },
        required_fields=["name", "website"],
        template_columns=TEMPLATE_COLUMNS,
        is_duplicate=True,
    )

    checks = _checks_by_key(result)
    blockers = _blockers_by_key(result)
    assert result.is_ready is False
    assert checks["required_critical_fields"].blocker_count == 1
    assert checks["duplicates"].blocker_count == 1
    assert checks["schema_match"].blocker_count == 2
    assert set(blockers) == {"required_critical_fields", "duplicates", "schema_match"}



def test_import_readiness_treats_whitespace_required_values_as_missing() -> None:
    result = evaluate_import_readiness(
        clean_payload={
            "name": "   ",
            "website": "https://example.edu",
        },
        required_fields=["name", "website"],
        template_columns=[
            {"name": "name", "order": 1},
            {"name": "website", "order": 2},
        ],
    )

    checks = _checks_by_key(result)
    assert result.is_ready is False
    assert checks["required_critical_fields"].passed is False
    assert checks["required_critical_fields"].blocker_count == 1



def test_import_readiness_skips_schema_block_when_template_columns_missing() -> None:
    result = evaluate_import_readiness(
        clean_payload={
            "name": "Example University",
            "unexpected": "value",
        },
        required_fields=["name"],
        template_columns=None,
        is_duplicate=False,
    )

    checks = _checks_by_key(result)
    assert result.is_ready is True
    assert checks["schema_match"].passed is True
    assert checks["schema_match"].blocker_count == 0



def test_import_readiness_is_ready_for_empty_payload_when_no_requirements_exist() -> None:
    result = evaluate_import_readiness(
        clean_payload={},
        required_fields=None,
        template_columns=None,
        is_duplicate=False,
    )

    assert result.is_ready is True
    assert result.blockers == []
    assert all(check.passed for check in result.checks)
