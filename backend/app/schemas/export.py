from typing import Literal

from pydantic import BaseModel


class ExportRequest(BaseModel):
    format: Literal["csv", "xlsx"]
    include_metadata: bool = False


class ExportResponse(BaseModel):
    download_url: str
    schema_used: str
    total_exported: int
