from pydantic import BaseModel


class FieldToReview(BaseModel):
    field_name: str
    raw_value: str | int | float | bool | None
    suggested_value: str | int | float | bool | None
    confidence: float
    reason: str
    merge_source_id: str | None = None
    merge_source_name: str | None = None
    merge_from_secondary: bool = False
    merge_conflicts: list[dict] = []


class ReviewQueueItem(BaseModel):
    record_id: str
    raw_record_id: str
    overall_confidence: int | None
    fields_to_review: list[FieldToReview]


class ReviewQueueResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[ReviewQueueItem]
