import pytest
from types import SimpleNamespace

from app.services.review_apply import apply_review_action


def test_apply_review_action_accepts_extracted_value() -> None:
    record = SimpleNamespace(clean_payload={}, status="NEEDS_REVIEW")

    updated = apply_review_action(
        record,
        field_name="email",
        action="ACCEPT",
        extracted_value="info@example.edu",
        new_value=None,
    )

    assert updated.clean_payload["email"] == "info@example.edu"
    assert updated.status == "REVIEWED"


def test_apply_review_action_edits_value() -> None:
    record = SimpleNamespace(clean_payload={"email": "bad-email"}, status="NEEDS_REVIEW")

    updated = apply_review_action(
        record,
        field_name="email",
        action="EDIT",
        extracted_value="bad-email",
        new_value="info@example.edu",
    )

    assert updated.clean_payload["email"] == "info@example.edu"
    assert updated.status == "REVIEWED"


def test_apply_review_action_clears_value_for_reject() -> None:
    record = SimpleNamespace(clean_payload={"email": "bad-email"}, status="NEEDS_REVIEW")

    updated = apply_review_action(
        record,
        field_name="email",
        action="REJECT",
        extracted_value="bad-email",
        new_value=None,
    )

    assert updated.clean_payload["email"] is None
    assert updated.status == "REVIEWED"



def test_apply_review_action_clears_value_for_unknown() -> None:
    record = SimpleNamespace(clean_payload={"email": "bad-email"}, status="NEEDS_REVIEW")

    updated = apply_review_action(
        record,
        field_name="email",
        action="UNKNOWN",
        extracted_value="bad-email",
        new_value=None,
    )

    assert updated.clean_payload["email"] is None
    assert updated.status == "REVIEWED"



def test_apply_review_action_returns_none_when_record_missing() -> None:
    updated = apply_review_action(
        None,
        field_name="email",
        action="ACCEPT",
        extracted_value="info@example.edu",
        new_value=None,
    )

    assert updated is None


def test_apply_review_action_rejects_unknown_action() -> None:
    record = SimpleNamespace(clean_payload={}, status="NEEDS_REVIEW")

    with pytest.raises(ValueError):
        apply_review_action(
            record,
            field_name="email",
            action="SOMETHING_ELSE",
            extracted_value="bad-email",
            new_value=None,
        )



def test_apply_review_action_preserves_unrelated_payload_fields() -> None:
    record = SimpleNamespace(
        clean_payload={"email": "bad-email", "website": "https://example.edu"},
        status="NEEDS_REVIEW",
    )

    updated = apply_review_action(
        record,
        field_name="email",
        action="ACCEPT",
        extracted_value="info@example.edu",
        new_value=None,
    )

    assert updated.clean_payload == {
        "email": "info@example.edu",
        "website": "https://example.edu",
    }



def test_apply_review_action_allows_edit_to_clear_value() -> None:
    record = SimpleNamespace(clean_payload={"email": "bad-email"}, status="NEEDS_REVIEW")

    updated = apply_review_action(
        record,
        field_name="email",
        action="EDIT",
        extracted_value="bad-email",
        new_value=None,
    )

    assert updated.clean_payload["email"] is None
    assert updated.status == "REVIEWED"
