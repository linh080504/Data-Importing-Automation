from app.schemas.ai_output import AIJudgeOutput
from app.services.scoring import calculate_weighted_confidence


def _judge_output(status: str = "APPROVED") -> AIJudgeOutput:
    return AIJudgeOutput.model_validate(
        {
            "fields_validation": {
                "name": {
                    "is_correct": True,
                    "corrected_value": None,
                    "confidence": 95,
                    "reason": "High confidence",
                },
                "website": {
                    "is_correct": True,
                    "corrected_value": None,
                    "confidence": 88,
                    "reason": "Looks valid",
                },
                "email": {
                    "is_correct": False,
                    "corrected_value": "info@example.edu",
                    "confidence": 72,
                    "reason": "Low confidence correction",
                },
            },
            "overall_confidence": 90,
            "status": status,
            "summary": "Scored",
        }
    )


def test_scoring_auto_approves_when_overall_and_required_fields_pass() -> None:
    output = _judge_output()

    decision = calculate_weighted_confidence(
        output,
        required_fields=["name", "website"],
        field_weights={"name": 3, "website": 2, "email": 1},
    )

    assert decision.auto_approve is True
    assert decision.decision == "AUTO_APPROVE"
    assert decision.required_fields_ok is True


def test_scoring_blocks_auto_approve_when_required_field_too_low() -> None:
    output = AIJudgeOutput.model_validate(
        {
            "fields_validation": {
                "name": {
                    "is_correct": True,
                    "corrected_value": None,
                    "confidence": 70,
                    "reason": "Too low for required field",
                },
                "website": {
                    "is_correct": True,
                    "corrected_value": None,
                    "confidence": 88,
                    "reason": "Looks valid",
                },
            },
            "overall_confidence": 90,
            "status": "APPROVED",
            "summary": "Scored",
        }
    )

    decision = calculate_weighted_confidence(output, required_fields=["name", "website"])

    assert decision.auto_approve is False
    assert decision.decision == "NEEDS_REVIEW"
    assert decision.fields_below_required_threshold == ["name"]


def test_scoring_returns_reject_when_judge_rejects() -> None:
    output = _judge_output(status="REJECTED")

    decision = calculate_weighted_confidence(output, required_fields=["name"])

    assert decision.auto_approve is False
    assert decision.decision == "REJECT"
