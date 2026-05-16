from pydantic import BaseModel, Field


class FieldToReview(BaseModel):
    field_name: str
    raw_value: str | int | float | bool | None
    suggested_value: str | int | float | bool | None
    confidence: float
    reason: str
    source_excerpt: str | None = None
    evidence_url: str | None = None
    evidence_source: str | None = None
    evidence_required: bool = False
    merge_source_id: str | None = None
    merge_source_name: str | None = None
    merge_from_secondary: bool = False
    merge_conflicts: list[dict] = Field(default_factory=list)


class CrawledFieldSnapshot(BaseModel):
    field_name: str
    value: str | int | float | bool | None
    source_url: str | None = None
    source_name: str | None = None
    source_excerpt: str | None = None
    status: str = "captured"
    reason: str | None = None


class ReviewQueueItem(BaseModel):
    record_id: str
    raw_record_id: str
    display_name: str
    unique_key: str
    source_url: str | None = None
    source_name: str | None = None
    overall_confidence: int | None
    crawled_fields: list[CrawledFieldSnapshot] = Field(default_factory=list)
    fields_to_review: list[FieldToReview]


class ReviewQueueResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[ReviewQueueItem]
