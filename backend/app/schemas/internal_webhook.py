from pydantic import BaseModel


class N8NUpsertRecordPayload(BaseModel):
    job_id: str
    source_id: str
    unique_key: str
    record_hash: str
    raw_payload: dict
    critical_fields_extracted: dict
    overall_confidence: int
    status: str


class InternalWebhookResponse(BaseModel):
    action: str
    record_id: str | None = None
    raw_record_id: str | None = None
    ingest_action: str | None = None
    changed: bool | None = None
    should_process_ai: bool | None = None
    message: str | None = None
