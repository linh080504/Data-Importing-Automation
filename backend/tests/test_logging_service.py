from types import SimpleNamespace
from uuid import uuid4

from app.schemas.ai_output import AIExtractorOutput, AIJudgeOutput
from app.services.logging import log_ai_extraction
from app.services.scoring import calculate_weighted_confidence


class FakeSession:
    def __init__(self) -> None:
        self.added = []

    def add(self, obj):
        if not getattr(obj, "id", None):
            obj.id = str(uuid4())
        self.added.append(obj)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def test_log_ai_extraction_persists_outputs_and_scoring() -> None:
    extractor_output = AIExtractorOutput.model_validate(
        {
            "critical_fields": {
                "name": {
                    "value": "Example University",
                    "confidence": 0.95,
                    "source_excerpt": "Example University",
                }
            },
            "extraction_notes": ["from title"],
        }
    )
    judge_output = AIJudgeOutput.model_validate(
        {
            "fields_validation": {
                "name": {
                    "is_correct": True,
                    "corrected_value": None,
                    "confidence": 96,
                    "reason": "Matches source",
                }
            },
            "overall_confidence": 96,
            "status": "APPROVED",
            "summary": "Good",
        }
    )
    scoring = calculate_weighted_confidence(judge_output, required_fields=["name"])
    session = FakeSession()

    log = log_ai_extraction(
        session,
        raw_record_id="raw_123",
        extractor_output=extractor_output,
        judge_output=judge_output,
        scoring=scoring,
    )

    assert log.raw_record_id == "raw_123"
    assert log.ai_1_payload["critical_fields"]["name"]["value"] == "Example University"
    assert log.ai_2_validation["judge_output"]["status"] == "APPROVED"
    assert log.ai_2_validation["scoring"]["decision"] == "AUTO_APPROVE"
    assert log.overall_confidence == 96
    assert len(session.added) == 1
