from app.services.quality import calculate_quality_score


def _metrics_by_name(result):
    return {metric.name: metric.score for metric in result.metrics}


def test_quality_score_is_high_for_complete_valid_reviewed_record() -> None:
    result = calculate_quality_score(
        raw_payload={
            "name": "Example University",
            "website": "https://example.edu",
            "email": "info@example.edu",
        },
        clean_payload={
            "name": "Example University",
            "website": "https://example.edu",
            "email": "info@example.edu",
        },
        required_fields=["name", "website", "email"],
        is_duplicate=False,
        status="APPROVED",
    )

    metrics = _metrics_by_name(result)
    assert metrics == {
        "completeness": 100,
        "validity": 100,
        "consistency": 100,
        "uniqueness": 100,
        "review_completion": 100,
    }
    assert result.overall_score == 100


def test_quality_score_drops_for_missing_and_invalid_fields() -> None:
    result = calculate_quality_score(
        raw_payload={
            "name": "Example University",
            "website": "example.edu",
            "email": "bad-email",
        },
        clean_payload={
            "name": "Example University",
            "website": "example.edu",
            "email": "",
        },
        required_fields=["name", "website", "email"],
        is_duplicate=False,
        status="NEEDS_REVIEW",
    )

    metrics = _metrics_by_name(result)
    assert metrics["completeness"] == 67
    assert metrics["validity"] == 33
    assert metrics["consistency"] == 67
    assert metrics["uniqueness"] == 100
    assert metrics["review_completion"] == 0
    assert result.overall_score == 53


def test_quality_score_penalizes_duplicates_and_unreviewed_records() -> None:
    result = calculate_quality_score(
        raw_payload={"name": "Example University"},
        clean_payload={"name": "Example University"},
        required_fields=["name"],
        is_duplicate=True,
        status="NEEDS_REVIEW",
    )

    metrics = _metrics_by_name(result)
    assert metrics["completeness"] == 100
    assert metrics["validity"] == 100
    assert metrics["consistency"] == 100
    assert metrics["uniqueness"] == 0
    assert metrics["review_completion"] == 0
    assert result.overall_score == 60



def test_quality_score_marks_rejected_records_as_review_complete() -> None:
    result = calculate_quality_score(
        raw_payload={"name": "Example University"},
        clean_payload={"name": "Example University"},
        required_fields=["name"],
        is_duplicate=False,
        status="REJECTED",
    )

    metrics = _metrics_by_name(result)
    assert metrics["review_completion"] == 100
    assert result.overall_score == 100



def test_quality_score_defaults_to_full_completeness_without_required_fields() -> None:
    result = calculate_quality_score(
        raw_payload={"name": "Example University"},
        clean_payload={"name": ""},
        required_fields=[],
        is_duplicate=False,
        status=None,
    )

    metrics = _metrics_by_name(result)
    assert metrics["completeness"] == 100
    assert metrics["review_completion"] == 0



def test_quality_score_returns_full_consistency_when_payloads_do_not_overlap() -> None:
    result = calculate_quality_score(
        raw_payload={"source_name": "Registry"},
        clean_payload={"name": "Example University"},
        required_fields=["name"],
        is_duplicate=False,
        status="APPROVED",
    )

    metrics = _metrics_by_name(result)
    assert metrics["consistency"] == 100
