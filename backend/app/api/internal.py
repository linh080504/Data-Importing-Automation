import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.internal_webhook import InternalWebhookResponse, N8NUpsertRecordPayload
from app.services.raw_ingest import upsert_raw_record

router = APIRouter(prefix="/internal/webhook/n8n", tags=["internal-webhooks"])


@router.post("/upsert-record", response_model=InternalWebhookResponse)
def upsert_record_from_n8n(
    payload: N8NUpsertRecordPayload,
    request: Request,
    x_n8n_secret: str | None = Header(default=None, alias="X-N8N-Secret"),
    db: Session = Depends(get_db),
) -> InternalWebhookResponse:
    settings = get_settings()

    if not settings.internal_webhook_enabled:
        raise HTTPException(status_code=503, detail="Internal webhook is disabled")

    if not settings.n8n_webhook_secret:
        raise HTTPException(status_code=503, detail="Internal webhook secret is not configured")

    content_type = request.headers.get("content-type", "")
    if settings.n8n_allowed_content_type not in content_type:
        raise HTTPException(status_code=415, detail="Unsupported content type")

    header_name = settings.n8n_callback_header
    provided_secret = request.headers.get(header_name)
    if not provided_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook secret")

    if not secrets.compare_digest(provided_secret, settings.n8n_webhook_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")

    raw_result = upsert_raw_record(
        db,
        job_id=payload.job_id,
        source_id=payload.source_id,
        unique_key=payload.unique_key,
        raw_payload=payload.raw_payload,
        record_hash=payload.record_hash,
    )

    action = "UPSERT_APPROVED" if payload.overall_confidence >= 85 and payload.status == "APPROVED" else "QUEUED_FOR_REVIEW"
    should_process_ai = raw_result.changed
    if not should_process_ai:
        action = "SKIP_AI_NO_CHANGE"

    return InternalWebhookResponse(
        action=action,
        record_id=payload.unique_key,
        raw_record_id=raw_result.raw_record_id,
        ingest_action=raw_result.action,
        changed=raw_result.changed,
        should_process_ai=should_process_ai,
        message="Webhook payload accepted",
    )
