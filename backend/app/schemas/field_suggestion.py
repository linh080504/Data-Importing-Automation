from pydantic import BaseModel


class SuggestedField(BaseModel):
    name: str
    score: int
    reason: str


class FieldSuggestionResponse(BaseModel):
    template_id: str
    template_columns: list[str]
    suggested_critical_fields: list[str]
    suggested_fields_detail: list[SuggestedField]
    min_fields: int
    max_fields: int
    reasoning: str
