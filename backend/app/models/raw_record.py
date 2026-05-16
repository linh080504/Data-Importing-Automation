from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UUID_PK, new_uuid


class RawRecord(Base):
    __tablename__ = "raw_records"
    __table_args__ = (
        UniqueConstraint("job_id", "source_id", "unique_key", name="uq_raw_records_job_source_unique_key"),
        Index("ix_raw_records_record_hash", "record_hash"),
    )

    id: Mapped[str] = mapped_column(UUID_PK, primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(
        UUID_PK, ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        UUID_PK, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unique_key: Mapped[str] = mapped_column(Text, nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
