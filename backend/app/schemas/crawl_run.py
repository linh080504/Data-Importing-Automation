from pydantic import BaseModel


class CrawlJobRunResponse(BaseModel):
    job_id: str
    status: str
    total_records: int
    crawled: int
    extracted: int
    needs_review: int
    cleaned: int
    message: str
