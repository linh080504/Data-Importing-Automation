from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.raw_record import RawRecord


@dataclass
class RawIngestResult:
    raw_record_id: str
    action: str
    changed: bool


def compute_record_hash(payload: dict) -> str:
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def upsert_raw_record(
    db: Session,
    *,
    job_id: str,
    source_id: str,
    unique_key: str,
    raw_payload: dict,
    record_hash: str | None = None,
) -> RawIngestResult:
    final_hash = record_hash or compute_record_hash(raw_payload)

    existing = (
        db.query(RawRecord)
        .filter(
            RawRecord.job_id == job_id,
            RawRecord.source_id == source_id,
            RawRecord.unique_key == unique_key,
        )
        .one_or_none()
    )

    if existing is None:
        record = RawRecord(
            job_id=job_id,
            source_id=source_id,
            unique_key=unique_key,
            record_hash=final_hash,
            raw_payload=raw_payload,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return RawIngestResult(raw_record_id=str(record.id), action="INSERTED", changed=True)

    changed = existing.record_hash != final_hash
    existing.raw_payload = raw_payload
    existing.record_hash = final_hash
    db.add(existing)
    db.commit()
    db.refresh(existing)
    return RawIngestResult(
        raw_record_id=str(existing.id),
        action="UPDATED" if changed else "NO_CHANGE",
        changed=changed,
    )
