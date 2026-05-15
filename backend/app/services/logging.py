from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.models.ai_extraction_log import AIExtractionLog
from app.schemas.ai_output import AIExtractorOutput, AIJudgeOutput
from app.services.scoring import ScoringDecision


def log_ai_extraction(
    db: Session,
    *,
    raw_record_id: str,
    extractor_output: AIExtractorOutput,
    judge_output: AIJudgeOutput,
    scoring: ScoringDecision,
) -> AIExtractionLog:
    log = AIExtractionLog(
        raw_record_id=raw_record_id,
        ai_1_payload=extractor_output.model_dump(mode="json"),
        ai_2_validation={
            "judge_output": judge_output.model_dump(mode="json"),
            "scoring": asdict(scoring),
        },
        overall_confidence=scoring.overall_confidence,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
