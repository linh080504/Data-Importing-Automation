from __future__ import annotations

from dataclasses import dataclass

from app.services.validator import validate_critical_fields


@dataclass
class QualityMetric:
    name: str
    score: int


@dataclass
class QualityScore:
    overall_score: int
    metrics: list[QualityMetric]


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _calc_completeness(clean_payload: dict[str, object], required_fields: list[str]) -> int:
    if not required_fields:
        return 100
    filled = sum(1 for field in required_fields if not _is_empty(clean_payload.get(field)))
    return round((filled / len(required_fields)) * 100)


def _calc_validity(clean_payload: dict[str, object], required_fields: list[str]) -> int:
    validation = validate_critical_fields(clean_payload, required_fields=required_fields)
    if validation.is_valid:
        return 100

    total_fields = max(1, len(clean_payload))
    penalty = round((len(validation.issues) / total_fields) * 100)
    return max(0, 100 - penalty)


def _calc_consistency(raw_payload: dict[str, object], clean_payload: dict[str, object]) -> int:
    common_fields = set(raw_payload).intersection(clean_payload)
    if not common_fields:
        return 100

    unchanged = sum(1 for field in common_fields if raw_payload.get(field) == clean_payload.get(field))
    return round((unchanged / len(common_fields)) * 100)


def _calc_uniqueness(is_duplicate: bool) -> int:
    return 0 if is_duplicate else 100


def _calc_review_completion(status: str | None) -> int:
    if status in {"APPROVED", "REVIEWED"}:
        return 100
    if status == "REJECTED":
        return 100
    return 0


def calculate_quality_score(
    *,
    raw_payload: dict[str, object],
    clean_payload: dict[str, object],
    required_fields: list[str] | None = None,
    is_duplicate: bool = False,
    status: str | None = None,
) -> QualityScore:
    required = required_fields or []

    completeness = _calc_completeness(clean_payload, required)
    validity = _calc_validity(clean_payload, required)
    consistency = _calc_consistency(raw_payload, clean_payload)
    uniqueness = _calc_uniqueness(is_duplicate)
    review_completion = _calc_review_completion(status)

    metrics = [
        QualityMetric(name="completeness", score=completeness),
        QualityMetric(name="validity", score=validity),
        QualityMetric(name="consistency", score=consistency),
        QualityMetric(name="uniqueness", score=uniqueness),
        QualityMetric(name="review_completion", score=review_completion),
    ]
    overall = round(sum(metric.score for metric in metrics) / len(metrics))

    return QualityScore(overall_score=overall, metrics=metrics)
