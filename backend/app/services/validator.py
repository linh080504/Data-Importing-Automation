from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
PHONE_RE = re.compile(r"^[+\d][\d\s().-]{6,}$")


@dataclass
class ValidationIssue:
    field: str
    code: str
    message: str


@dataclass
class ValidationResult:
    is_valid: bool
    issues: list[ValidationIssue]


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def validate_critical_fields(
    extracted_fields: dict[str, object],
    *,
    required_fields: list[str] | None = None,
) -> ValidationResult:
    required = required_fields or []
    issues: list[ValidationIssue] = []

    for field in required:
        if _is_empty(extracted_fields.get(field)):
            issues.append(ValidationIssue(field=field, code="required_missing", message="Required field is missing"))

    for field, value in extracted_fields.items():
        if _is_empty(value):
            continue
        text = str(value).strip()
        lower = field.lower()

        if "email" in lower and not EMAIL_RE.match(text):
            issues.append(ValidationIssue(field=field, code="invalid_email", message="Invalid email format"))

        if "website" in lower or "url" in lower or "link" in lower:
            if not URL_RE.match(text):
                issues.append(ValidationIssue(field=field, code="invalid_url", message="Invalid URL format"))

        if "phone" in lower or "contact" in lower:
            compact = re.sub(r"\s+", " ", text)
            if not PHONE_RE.match(compact):
                issues.append(ValidationIssue(field=field, code="invalid_phone", message="Invalid phone format"))

    return ValidationResult(is_valid=len(issues) == 0, issues=issues)
