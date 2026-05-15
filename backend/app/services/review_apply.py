from __future__ import annotations

from app.models.clean_record import CleanRecord


def apply_review_action(
    clean_record: CleanRecord | object | None,
    *,
    field_name: str,
    action: str,
    extracted_value: object,
    new_value: object | None,
) -> object | None:
    if clean_record is None:
        return None

    clean_payload = dict(getattr(clean_record, "clean_payload", {}) or {})

    if action == "ACCEPT":
        clean_payload[field_name] = extracted_value
    elif action == "EDIT":
        clean_payload[field_name] = new_value
    elif action in {"REJECT", "UNKNOWN"}:
        clean_payload[field_name] = None
    else:
        raise ValueError(f"Unsupported review action: {action}")

    clean_record.clean_payload = clean_payload
    clean_record.status = "REVIEWED"
    return clean_record
