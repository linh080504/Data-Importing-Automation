from types import SimpleNamespace

from app.services.ai_extractor import AIExtractorOutput, extract_critical_fields, ExtractRequest
from app.services.direct_run import PreparedRow, RuleBasedExtractorClient, _build_clean_candidate_from_row


def test_rule_based_extractor_coerces_list_values_to_scalar() -> None:
    output = extract_critical_fields(
        ExtractRequest(raw_text="{}", critical_fields=["website"]),
        client=RuleBasedExtractorClient({"website": ["https://example.edu"]}, ["website"]),
    )

    assert isinstance(output, AIExtractorOutput)
    assert output.critical_fields["website"].value == "https://example.edu"


def test_source_clean_candidate_uses_focus_fields_and_evidence_backed_template_fields() -> None:
    prepared_row = PreparedRow(
        normalized={
            "name": "Example University",
            "website": "https://example.edu",
            "campus_student_life": "Library, labs",
            "financials": None,
            "sponsored": None,
        },
        raw_payload={
            "name": "Example University",
            "website": "https://example.edu",
            "campus_student_life": "Library, labs",
            "source_url": "https://example.edu/about",
        },
        raw_text="Example University has Library, labs. Website https://example.edu",
        unique_key="example",
    )

    output = _build_clean_candidate_from_row(
        prepared_row,
        ["name", "financials"],
        [
            {"name": "id", "order": 1},
            {"name": "name", "order": 2},
            {"name": "slug", "order": 3},
            {"name": "website", "order": 4},
            {"name": "financials", "order": 5},
            {"name": "campus_student_life", "order": 6},
            {"name": "sponsored", "order": 7},
        ],
    )

    assert list(output.critical_fields) == ["name", "financials", "website", "campus_student_life"]
    assert output.critical_fields["financials"].value is None
    assert output.critical_fields["website"].value == "https://example.edu"
    assert output.critical_fields["campus_student_life"].evidence_url == "https://example.edu/about"
    assert "id" not in output.critical_fields
    assert "slug" not in output.critical_fields
    assert "sponsored" not in output.critical_fields
