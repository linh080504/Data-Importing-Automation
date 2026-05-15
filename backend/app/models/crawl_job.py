from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UUID_PK, new_uuid


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[str] = mapped_column(UUID_PK, primary_key=True, default=new_uuid)
    country: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="QUEUED", index=True)
    source_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    crawl_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="trusted_sources")
    discovery_input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    critical_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    clean_template_id: Mapped[str] = mapped_column(UUID_PK, nullable=False)
    ai_assist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    progress: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
