from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CrawlPromptDiscoveryInput(BaseModel):
    prompt_text: str = Field(min_length=1)
    prompt_source: Literal["pdf", "manual"] = "manual"
    seed_sources: list[str] = Field(default_factory=list)


class CrawlTrustedSourceDiscoveryInput(BaseModel):
    selected_source_ids: list[str] = Field(default_factory=list)
    source_plan: dict[str, Any] | None = None


class CrawlDiscoveryInput(BaseModel):
    prompt_text: str | None = None
    prompt_source: Literal["pdf", "manual"] | None = None
    seed_sources: list[str] = Field(default_factory=list)
    selected_source_ids: list[str] = Field(default_factory=list)
    source_plan: dict[str, Any] | None = None

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class CrawlModeInfo(BaseModel):
    mode: Literal["trusted_sources", "prompt_discovery", "supplemental_discovery"]
    discovery_input: CrawlDiscoveryInput | None = None


class CrawlJobCreate(BaseModel):
    country: str
    source_ids: list[str] = Field(min_length=0, default_factory=list)
    crawl_mode: Literal["trusted_sources", "prompt_discovery", "supplemental_discovery"] = "trusted_sources"
    discovery_input: CrawlDiscoveryInput | None = None
    critical_fields: list[str] = Field(min_length=3, max_length=30)
    clean_template_id: str
    ai_assist: bool = True

    def resolved_discovery_input(self) -> dict[str, Any]:
        payload = self.discovery_input.as_payload() if self.discovery_input is not None else {}
        if self.crawl_mode == "trusted_sources" and not payload.get("selected_source_ids"):
            payload["selected_source_ids"] = list(self.source_ids)
        return payload

    def model_post_init(self, __context: Any) -> None:
        if self.crawl_mode == "prompt_discovery":
            prompt_text = (self.discovery_input.prompt_text if self.discovery_input else None) or ""
            if not prompt_text.strip():
                raise ValueError("discovery_input.prompt_text is required for prompt_discovery mode")
        if self.crawl_mode == "supplemental_discovery" and self.discovery_input is not None:
            payload = self.resolved_discovery_input()
            supplemental_plan = payload.get("supplemental_plan") if isinstance(payload, dict) else None
            if supplemental_plan is None:
                return
            if not isinstance(supplemental_plan, dict) or not isinstance(supplemental_plan.get("sources"), list) or not supplemental_plan.get("sources"):
                raise ValueError("discovery_input.supplemental_plan.sources must be a non-empty list when supplemental_plan is provided")


class CrawlJobCreateResponse(BaseModel):
    job_id: str
    status: str
    message: str
    crawl_mode: str = "trusted_sources"
    discovery_input: dict[str, Any] | None = None
    total_records: int
    crawled: int
    extracted: int
    needs_review: int
    cleaned: int
    skipped: int = 0
    clean_candidates: int = 0
    approved: int = 0
    rejected: int = 0


class CrawlJobProgress(BaseModel):
    total_records: int
    crawled: int
    extracted: int
    needs_review: int
    cleaned: int
    skipped: int = 0
    clean_candidates: int = 0
    approved: int = 0
    rejected: int = 0
    processed: int | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.processed is None:
            self.processed = self.extracted
        if self.clean_candidates == 0 and self.cleaned > 0:
            self.clean_candidates = self.cleaned
        if self.approved == 0 and self.cleaned > 0 and self.needs_review == 0 and self.rejected == 0:
            self.approved = self.cleaned


class CrawlJobQualitySummary(BaseModel):
    clean_candidates: int
    approved_count: int
    needs_review_count: int
    rejected_count: int
    quality_score: int | None


class CrawlJobListItem(BaseModel):
    job_id: str
    country: str
    status: str
    source_names: list[str]
    template_name: str | None
    crawl_mode: str = "trusted_sources"
    discovery_input: dict[str, Any] | None = None
    updated_at: str
    total_records: int
    clean_records: int
    clean_candidates: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    needs_review_count: int
    quality_score: int | None
    progress: CrawlJobProgress | None = None
    quality_summary: CrawlJobQualitySummary | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.clean_candidates == 0 and self.clean_records > 0:
            self.clean_candidates = self.clean_records
        if self.quality_summary is None:
            self.quality_summary = CrawlJobQualitySummary(
                clean_candidates=self.clean_candidates,
                approved_count=self.approved_count,
                needs_review_count=self.needs_review_count,
                rejected_count=self.rejected_count,
                quality_score=self.quality_score,
            )
        if self.progress is None:
            self.progress = CrawlJobProgress(
                total_records=self.total_records,
                crawled=0,
                extracted=0,
                needs_review=self.needs_review_count,
                cleaned=self.clean_records,
                clean_candidates=self.clean_candidates,
                approved=self.approved_count,
                rejected=self.rejected_count,
            )


class CrawlJobListResponse(BaseModel):
    items: list[CrawlJobListItem]


class CrawlJobDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    country: str
    status: str
    source_names: list[str]
    template_name: str | None
    template_columns: list[str] = Field(default_factory=list)
    crawl_mode: str = "trusted_sources"
    discovery_input: dict[str, Any] | None = None
    updated_at: str
    progress: CrawlJobProgress
    clean_records: int
    clean_candidates: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    needs_review_count: int
    quality_score: int | None
    quality_summary: CrawlJobQualitySummary | None = None
    critical_fields: list[str] | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.clean_candidates == 0 and self.clean_records > 0:
            self.clean_candidates = self.clean_records
        if self.quality_summary is None:
            self.quality_summary = CrawlJobQualitySummary(
                clean_candidates=self.clean_candidates,
                approved_count=self.approved_count,
                needs_review_count=self.needs_review_count,
                rejected_count=self.rejected_count,
                quality_score=self.quality_score,
            )
        if self.progress.clean_candidates == 0 and self.clean_candidates > 0:
            self.progress.clean_candidates = self.clean_candidates
        if self.progress.approved == 0 and self.approved_count > 0:
            self.progress.approved = self.approved_count
        if self.progress.rejected == 0 and self.rejected_count > 0:
            self.progress.rejected = self.rejected_count
        if self.progress.processed is None:
            self.progress.processed = self.progress.extracted
