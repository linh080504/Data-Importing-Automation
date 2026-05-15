from pydantic import BaseModel


class ImportResponse(BaseModel):
    job_id: str
    status: str
    message: str
    inserted_records: int
    updated_records: int
    duplicate_records: int
    total_records: int
    imported_records: int
