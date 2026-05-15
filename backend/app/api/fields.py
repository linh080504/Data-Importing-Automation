from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.clean_template import CleanTemplate
from app.schemas.field_suggestion import FieldSuggestionResponse, SuggestedField
from app.services.field_suggester import MAX_CRITICAL_FIELDS_MVP, MIN_CRITICAL_FIELDS, suggest_critical_fields

router = APIRouter(prefix="/fields", tags=["fields"])


@router.get("/suggest/{template_id}", response_model=FieldSuggestionResponse)
def suggest_fields(template_id: str, db: Session = Depends(get_db)) -> FieldSuggestionResponse:
    template = db.query(CleanTemplate).filter(CleanTemplate.id == template_id).one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    suggestions = suggest_critical_fields(template.columns)
    return FieldSuggestionResponse(
        template_id=str(template.id),
        suggested_critical_fields=[item.name for item in suggestions],
        suggested_fields_detail=[
            SuggestedField(name=item.name, score=item.score, reason=item.reason) for item in suggestions
        ],
        min_fields=MIN_CRITICAL_FIELDS,
        max_fields=MAX_CRITICAL_FIELDS_MVP,
        reasoning="MVP currently uses a deterministic field-priority engine based on template column names. This keeps suggestions stable and reviewable before wiring a full LLM-based suggester.",
    )
