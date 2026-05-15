from __future__ import annotations

from dataclasses import dataclass

from app.schemas.ai_output import AIJudgeOutput

AUTO_APPROVE_THRESHOLD = 85
REQUIRED_FIELD_MIN_CONFIDENCE = 80


@dataclass
class ScoringDecision:
    overall_confidence: int
    required_fields_ok: bool
    auto_approve: bool
    fields_below_required_threshold: list[str]
    decision: str


def calculate_weighted_confidence(
    judge_output: AIJudgeOutput,
    *,
    required_fields: list[str] | None = None,
    field_weights: dict[str, int] | None = None,
) -> ScoringDecision:
    required = set(required_fields or [])
    weights = field_weights or {}

    total_weight = 0
    weighted_sum = 0
    below_threshold: list[str] = []

    for field_name, result in judge_output.fields_validation.items():
        weight = weights.get(field_name, 1)
        total_weight += weight
        weighted_sum += result.confidence * weight
        if field_name in required and result.confidence < REQUIRED_FIELD_MIN_CONFIDENCE:
            below_threshold.append(field_name)

    if total_weight == 0:
        overall = judge_output.overall_confidence
    else:
        overall = round(weighted_sum / total_weight)

    required_fields_ok = len(below_threshold) == 0
    auto_approve = overall >= AUTO_APPROVE_THRESHOLD and required_fields_ok and judge_output.status == "APPROVED"

    if auto_approve:
        decision = "AUTO_APPROVE"
    elif judge_output.status == "REJECTED":
        decision = "REJECT"
    else:
        decision = "NEEDS_REVIEW"

    return ScoringDecision(
        overall_confidence=overall,
        required_fields_ok=required_fields_ok,
        auto_approve=auto_approve,
        fields_below_required_threshold=below_threshold,
        decision=decision,
    )
