from pydantic import BaseModel


class CompareField(BaseModel):
    field_name: str
    raw_value: str | int | float | bool | None
    clean_value: str | int | float | bool | None
    merge_source_id: str | None = None
    merge_source_name: str | None = None
    merge_from_secondary: bool = False
    merge_conflicts: list[dict] = []


class CompareRecord(BaseModel):
    raw_record_id: str
    unique_key: str
    status: str | None
    quality_score: int | None
    fields: list[CompareField]


class CompareResponse(BaseModel):
    total: int
    items: list[CompareRecord]
