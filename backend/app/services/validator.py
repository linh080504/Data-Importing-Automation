from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
PHONE_RE = re.compile(r"^[+\d][\d\s().-]{6,}$")
FINANCIAL_KEYWORD_RE = re.compile(
    r"\b("
    r"tuition|tuition fee|tuition fees|fee|fees|cost of attendance|costs?|"
    r"hoc phi|học phí|le phi|lệ phí|school fee|school fees"
    r")\b",
    re.IGNORECASE,
)
FINANCIAL_AMOUNT_RE = re.compile(
    r"("
    r"[$€£¥₩₫đ]\s*\d|"
    r"\d[\d.,]*(?:\s*(?:-|to|–|—)\s*\d[\d.,]*)?\s*"
    r"(?:vnd|vnđ|usd|inr|eur|gbp|aud|cad|sgd|thb|myr|jpy|krw|cny|rmb|"
    r"triệu|trieu|million|lakh|crore|k)\b|"
    r"\b(?:vnd|vnđ|usd|inr|eur|gbp|aud|cad|sgd|thb|myr|jpy|krw|cny|rmb)\s*"
    r"\d[\d.,]*"
    r")",
    re.IGNORECASE,
)


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


def _digits_only(value: str) -> str:
    return re.sub(r"\D+", "", value)


def _has_sequential_digits(digits: str) -> bool:
    if len(digits) < 6:
        return False
    sequences = ("0123456789", "1234567890", "9876543210", "0987654321")
    return any(digits in sequence or sequence in digits for sequence in sequences)


def is_plausible_phone_number(value: object) -> bool:
    if _is_empty(value):
        return False
    text = re.sub(r"\s+", " ", str(value).strip())
    if not PHONE_RE.match(text):
        return False
    digits = _digits_only(text)
    if len(digits) < 8 or len(digits) > 15:
        return False
    local_digits = digits[-10:]
    if len(set(digits)) == 1 or len(set(local_digits)) == 1:
        return False
    if re.search(r"(\d)\1{5,}", digits):
        return False
    if _has_sequential_digits(digits) or _has_sequential_digits(local_digits):
        return False
    placeholder_values = {
        "00000000",
        "000000000",
        "0000000000",
        "11111111",
        "111111111",
        "1111111111",
        "12345678",
        "123456789",
        "1234567890",
        "0123456789",
        "0987654321",
    }
    return digits not in placeholder_values and local_digits not in placeholder_values


def looks_like_tuition_financials(value: object) -> bool:
    if _is_empty(value):
        return False
    text = re.sub(r"\s+", " ", str(value).strip())
    if len(text) > 320:
        return False
    has_amount = FINANCIAL_AMOUNT_RE.search(text) is not None
    if not has_amount:
        return False
    has_keyword = FINANCIAL_KEYWORD_RE.search(text) is not None
    if has_keyword:
        return True
    return len(text) <= 120


def _canonical_country(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    normalized = " ".join(text.split())
    if normalized in {"viet nam", "vn"}:
        return "vietnam"
    if normalized in {"us", "usa", "united states of america"}:
        return "united states"
    return normalized


def _looks_like_generic_taxonomy_text(text: str) -> bool:
    lowered = text.lower()
    generic_markers = [
        "private universities and private colleges are",
        "may be contrasted with public universities",
        "higher education institutions not operated",
    ]
    return any(marker in lowered for marker in generic_markers)


def validate_critical_fields(
    extracted_fields: dict[str, object],
    *,
    required_fields: list[str] | None = None,
    expected_country: str | None = None,
) -> ValidationResult:
    required = required_fields or []
    issues: list[ValidationIssue] = []

    for field in required:
        if _is_empty(extracted_fields.get(field)):
            issues.append(ValidationIssue(field=field, code="required_missing", message="Required field is missing"))

    expected_country_key = _canonical_country(expected_country) if expected_country else ""

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

        if "phone" in lower:
            if not is_plausible_phone_number(text):
                issues.append(ValidationIssue(field=field, code="invalid_phone", message="Invalid phone format or placeholder value"))
        elif lower == "admissions_contact":
            if not EMAIL_RE.match(text) and not is_plausible_phone_number(text):
                issues.append(ValidationIssue(field=field, code="invalid_contact", message="Admissions contact must be a valid email or phone number"))

        if lower == "financials" and not looks_like_tuition_financials(text):
            issues.append(
                ValidationIssue(
                    field=field,
                    code="invalid_financials",
                    message="Financials must be an annual tuition/fee amount or range with source evidence",
                )
            )

        if lower in {"description", "campus_student_life"} and _looks_like_generic_taxonomy_text(text):
            issues.append(
                ValidationIssue(
                    field=field,
                    code="generic_content",
                    message="Generic taxonomy text is not allowed for institution-specific fields",
                )
            )

        if lower == "country" and expected_country_key:
            actual_country_key = _canonical_country(text)
            if actual_country_key and actual_country_key != expected_country_key:
                issues.append(
                    ValidationIssue(
                        field=field,
                        code="country_mismatch",
                        message="Extracted country does not match crawl job country",
                    )
                )

    return ValidationResult(is_valid=len(issues) == 0, issues=issues)
