from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UUID_PK, new_uuid


class CleanRecord(Base):
    __tablename__ = "clean_records"
    __table_args__ = (
        UniqueConstraint("job_id", "unique_key", name="uq_clean_records_job_unique_key"),
        Index("ix_clean_records_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID_PK, primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(
        UUID_PK, ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_record_id: Mapped[str | None] = mapped_column(
        UUID_PK, ForeignKey("raw_records.id", ondelete="SET NULL"), nullable=True, index=True
    )
    unique_key: Mapped[str] = mapped_column(Text, nullable=False)
    clean_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NEEDS_REVIEW")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
