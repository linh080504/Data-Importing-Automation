from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UUID_PK, new_uuid


class AIExtractionLog(Base):
    __tablename__ = "ai_extraction_logs"

    id: Mapped[str] = mapped_column(UUID_PK, primary_key=True, default=new_uuid)
    raw_record_id: Mapped[str] = mapped_column(
        UUID_PK, ForeignKey("raw_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ai_1_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_2_validation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    overall_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
